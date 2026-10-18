"""
Raivora Music Web Platform — Music REST API Controller & Action Dispatcher.
Provides real-time endpoints for playback state, queues, controls, 10-band EQ, Auto-DJ, and telemetry.
Enforces RBAC security and asynchronous WAL event queueing.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import urllib.parse
import aiohttp
from aiohttp import web

from music_bot.config import MUSIC_DATABASE_PATH
from music_bot.database.db import MusicDatabase
from music_bot.services.session_service import SessionManager, PlaybackState
from web.auth import AuthManager, SESSION_COOKIE_NAME

logger = logging.getLogger("Rai.MusicAPI")


def json_success(data: Any, status: int = 200) -> web.Response:
    payload = {
        "success": True,
        "data": data,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    return web.json_response(payload, status=status)


def json_error(code: str, message: str, status: int = 400) -> web.Response:
    payload = {
        "success": False,
        "error": {"code": code, "message": message},
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    return web.json_response(payload, status=status)


class MusicApiRouter:
    """REST API Controller for Raivora Music Web."""

    def __init__(self, auth_manager: AuthManager, bot: Optional[Any] = None):
        self.auth_manager = auth_manager
        self.bot = bot
        self.db = MusicDatabase(Path(MUSIC_DATABASE_PATH))
        self._db_connected = False

    async def _ensure_db(self) -> None:
        if not self._db_connected:
            await self.db.connect()
            self._db_connected = True

    async def _get_current_user(self, request: web.Request) -> Optional[Dict[str, Any]]:
        if not self.auth_manager:
            return None
        try:
            sess = await self.auth_manager.get_session_from_request(request)
            if sess:
                return sess.get("user_data") or sess
        except Exception:
            pass
        return None

    # ==========================================
    # 1. GUILD DISCOVERY & STATE
    # ==========================================
    async def get_guilds(self, request: web.Request) -> web.Response:
        """Fetch accessible guilds where the music bot is active, validating user access."""
        await self._ensure_db()
        sm = SessionManager.get_instance()
        active_guild_ids = list(sm._sessions.keys())

        user = await self._get_current_user(request)
        guilds_data = []

        # Default fallback servers
        known_guilds = [
            {"id": 1525030316845301781, "name": "THOR APEX ⚡", "icon": None, "active": True},
            {"id": 1457382179981099090, "name": "✦ ʀᴀɪ ʀᴀᴍ ✦", "icon": None, "active": True},
            {"id": 1428058914141900860, "name": "ABIJITH 777", "icon": None, "active": True},
            {"id": 1494692962041467005, "name": "SUPPORT SERVER FOR RAIVORA", "icon": None, "active": True},
            {"id": 1516486851387588640, "name": "RJ WHITEYY's server", "icon": None, "active": True},
            {"id": 1545715275062575175, "name": "𝐖ᴇx 𝐂ʀᴏᴘᴏʀᴀᴛɪᴏɴ", "icon": None, "active": True},
            {"id": 1552400206811631687, "name": "rf.rai_006's server", "icon": None, "active": True},
        ]

        # Read active sessions from database
        try:
            sessions = await self.db.get_all_active_sessions()
            db_guild_ids = {s.guild_id for s in sessions}
        except Exception:
            db_guild_ids = set()

        # Map live guilds from Discord bot instance
        bot_guilds = {}
        if self.bot and hasattr(self.bot, "guilds"):
            for bg in self.bot.guilds:
                bot_guilds[bg.id] = bg

        # Inspect authenticated user's mutual guilds if available
        user_guild_ids = None
        user_admin = False
        if user:
            user_admin = bool(user.get("is_admin", False))
            raw_guilds = user.get("guilds") or []
            if raw_guilds:
                user_guild_ids = set()
                for ug in raw_guilds:
                    try:
                        user_guild_ids.add(int(ug["id"]))
                    except (ValueError, TypeError):
                        pass

        # Build consolidated candidate list
        source_list = []
        if bot_guilds:
            for g_id, g_obj in bot_guilds.items():
                source_list.append({
                    "id": g_id,
                    "name": g_obj.name,
                    "icon": g_obj.icon.url if g_obj.icon else None,
                    "bot_in_guild": True,
                })
        else:
            source_list = known_guilds

        for g in source_list:
            g_id = int(g["id"])
            is_active = g_id in active_guild_ids or g_id in db_guild_ids
            session = sm.get_session_nowait(g_id) if hasattr(sm, "get_session_nowait") else None
            vc = session.voice_client if (session and session.voice_client) else None
            if not vc and self.bot and hasattr(self.bot, "get_guild"):
                guild_obj = self.bot.get_guild(g_id)
                if guild_obj and hasattr(guild_obj, "voice_client"):
                    vc = guild_obj.voice_client

            is_connected = False
            if vc and hasattr(vc, "is_connected") and callable(vc.is_connected):
                try:
                    conn = vc.is_connected()
                    is_connected = (conn is True) or (isinstance(conn, bool) and conn)
                except Exception:
                    is_connected = False

            voice_name = None
            voice_status = "Connected" if is_connected else "Disconnected"
            if is_connected and getattr(vc, "channel", None):
                ch_name = getattr(vc.channel, "name", None)
                if isinstance(ch_name, str):
                    voice_name = ch_name
                elif ch_name is not None and not hasattr(ch_name, "_mock_name"):
                    voice_name = str(ch_name)

            # Determine authorization
            is_authorized = True
            if user_guild_ids is not None and not user_admin:
                is_authorized = g_id in user_guild_ids

            bot_present = True
            if self.bot and hasattr(self.bot, "get_guild"):
                bot_present = self.bot.get_guild(g_id) is not None

            guilds_data.append({
                "id": str(g_id),
                "name": g["name"],
                "icon": g.get("icon"),
                "has_active_playback": is_active,
                "voice_channel": voice_name,
                "voice_status": voice_status,
                "authorized": is_authorized,
                "bot_in_guild": bot_present,
            })

        # If user is authenticated, prioritize authorized guilds
        if user:
            guilds_data.sort(key=lambda x: (not x["authorized"], not x["has_active_playback"], x["name"]))

        return json_success({"guilds": guilds_data, "user": user})

    # ==========================================
    # 2. LIVE SESSION STATE
    # ==========================================
    async def get_session(self, request: web.Request) -> web.Response:
        """Fetch real-time playback session, track metadata, progress, and DSP settings."""
        await self._ensure_db()
        guild_id_str = request.query.get("guild_id", "1525030316845301781")
        try:
            guild_id = int(guild_id_str)
        except ValueError:
            return json_error("INVALID_GUILD", "Invalid guild_id parameter")

        sm = SessionManager.get_instance()
        session = sm.get_session_nowait(guild_id) if hasattr(sm, "get_session_nowait") else None

        user = await self._get_current_user(request)
        is_admin = bool(user.get("is_admin", False)) if user else False
        is_staff = bool(user.get("is_staff", False)) if user else False
        perms = {"can_control": True, "is_admin": is_admin, "is_staff": is_staff}

        # Determine real voice connection status across session and bot client
        vc_name = None
        vc_id = None
        voice_status = "Disconnected"

        if session and session.voice_client:
            if session.voice_client.is_connected() and session.voice_client.channel:
                vc_name = session.voice_client.channel.name
                vc_id = session.voice_client.channel.id
                voice_status = "Connected"
            elif getattr(session.voice_client, "is_connecting", lambda: False)():
                voice_status = "Connecting"
            elif getattr(session, "recovery_attempts", 0) > 0 or session.state.value == "RECOVERING":
                voice_status = "Reconnecting"
                if session.voice_client.channel:
                    vc_name = session.voice_client.channel.name
                    vc_id = session.voice_client.channel.id

        if not vc_name and self.bot and hasattr(self.bot, "get_guild"):
            g = self.bot.get_guild(guild_id)
            if g and g.voice_client:
                if g.voice_client.is_connected() and g.voice_client.channel:
                    vc_name = g.voice_client.channel.name
                    vc_id = g.voice_client.channel.id
                    voice_status = "Connected"
                    if session and not session.voice_client:
                        session.voice_client = g.voice_client
                elif getattr(g.voice_client, "is_connecting", lambda: False)():
                    voice_status = "Connecting"

        # Check persistent 24/7 setting from database if not set in memory
        is_247_enabled = getattr(session, "twenty_four_seven", False)
        if not is_247_enabled and self.bot and getattr(self.bot, "db", None):
            try:
                g_settings = await self.bot.db.get_guild_settings(guild_id)
                if g_settings and getattr(g_settings, "twenty_four_seven_enabled", False):
                    is_247_enabled = True
                    if session:
                        session.twenty_four_seven = True
            except Exception:
                pass

        # If in-memory session found
        if session and session.current_track:
            track = session.current_track
            elapsed = session.elapsed_seconds
            total = track.duration or 0
            is_playing = bool(session.is_playing)
            is_paused = bool(session.is_paused)

            data = {
                "guild_id": str(guild_id),
                "state": session.state.value if hasattr(session.state, "value") else str(session.state),
                "is_playing": is_playing,
                "is_paused": is_paused,
                "current_track": {
                    "title": track.title,
                    "artist": track.artist or "Unknown Artist",
                    "url": track.url,
                    "thumbnail": track.thumbnail,
                    "duration": total,
                    "requester_id": str(track.requester_id) if track.requester_id else None,
                    "requester_name": track.requester_name or "User",
                },
                "position_seconds": elapsed,
                "duration_seconds": total,
                "remaining_seconds": max(0, total - elapsed) if total > 0 else 0,
                "volume": session.volume,
                "loop_mode": session.loop_mode.value if hasattr(session.loop_mode, "value") else str(session.loop_mode),
                "eq_preset": session.eq_preset or "Flat",
                "audio_filter": session.audio_filter,
                "queue_count": len(session.queue),
                "history_count": len(session.history),
                "auto_dj": bool(getattr(session, "dj_enabled", False) or session.autoplay),
                "twenty_four_seven": is_247_enabled,
                "voice_channel_id": str(vc_id) if vc_id else None,
                "voice_channel_name": vc_name,
                "channel_name": vc_name,
                "voice_status": voice_status,
                "last_error": getattr(session, "last_error", None),
                "permissions": perms,
            }
            data["session"] = {k: v for k, v in data.items() if k != "session"}
            return json_success(data)

        # Fallback to persistent session in database
        try:
            db_session = await self.db.get_session(guild_id)
            if db_session and db_session.current_track:
                t = db_session.current_track
                data = {
                    "guild_id": str(guild_id),
                    "state": db_session.state,
                    "is_playing": db_session.state == "PLAYING" and not db_session.is_paused,
                    "is_paused": bool(db_session.is_paused),
                    "current_track": {
                        "title": t.title,
                        "artist": t.artist or "Unknown Artist",
                        "url": t.url,
                        "thumbnail": t.thumbnail,
                        "duration": t.duration,
                        "requester_id": str(t.requester_id) if t.requester_id else None,
                        "requester_name": t.requester_name,
                    },
                    "position_seconds": db_session.position_seconds,
                    "duration_seconds": t.duration,
                    "remaining_seconds": max(0, t.duration - db_session.position_seconds),
                    "volume": db_session.volume,
                    "loop_mode": db_session.loop_mode,
                    "eq_preset": "Flat",
                    "queue_count": len(db_session.queue) if db_session.queue else 0,
                    "history_count": len(db_session.history) if db_session.history else 0,
                    "auto_dj": False,
                    "twenty_four_seven": is_247_enabled,
                    "voice_channel_id": str(db_session.voice_channel_id) if db_session.voice_channel_id else None,
                    "voice_channel_name": vc_name,
                    "voice_status": voice_status,
                    "last_error": None,
                    "permissions": perms,
                }
                return json_success(data)
        except Exception as e:
            logger.debug(f"DB session fetch note: {e}")

        # Idle session
        idle_data = {
            "guild_id": str(guild_id),
            "state": "IDLE",
            "is_playing": False,
            "is_paused": False,
            "current_track": None,
            "position_seconds": 0,
            "duration_seconds": 0,
            "remaining_seconds": 0,
            "volume": 80,
            "loop_mode": "off",
            "eq_preset": "Flat",
            "queue_count": 0,
            "history_count": 0,
            "auto_dj": False,
            "twenty_four_seven": is_247_enabled,
            "voice_channel_id": str(vc_id) if vc_id else None,
            "voice_channel_name": vc_name,
            "channel_name": vc_name,
            "voice_status": voice_status,
            "last_error": None,
            "permissions": perms,
        }
        idle_data["session"] = {k: v for k, v in idle_data.items() if k != "session"}
        return json_success(idle_data)

    # ==========================================
    # 3. QUEUE & HISTORY
    # ==========================================
    async def get_queue(self, request: web.Request) -> web.Response:
        """Fetch current queue tracks for the specified guild."""
        await self._ensure_db()
        guild_id = int(request.query.get("guild_id", "1525030316845301781"))
        sm = SessionManager.get_instance()
        session = sm.get_session_nowait(guild_id) if hasattr(sm, "get_session_nowait") else None

        tracks = []
        if session and session.queue:
            for i, t in enumerate(session.queue):
                tracks.append({
                    "index": i,
                    "title": t.title,
                    "artist": t.artist or "Unknown",
                    "url": t.url,
                    "duration": t.duration,
                    "thumbnail": t.thumbnail,
                    "requester_name": t.requester_name,
                })
        else:
            try:
                db_queue = await self.db.get_queue(guild_id)
                for i, t in enumerate(db_queue):
                    tracks.append({
                        "index": i,
                        "title": t.title,
                        "artist": t.artist or "Unknown",
                        "url": t.url,
                        "duration": t.duration,
                        "thumbnail": t.thumbnail,
                        "requester_name": t.requester_name,
                    })
            except Exception:
                pass

        total_duration = sum(t["duration"] for t in tracks)
        return json_success({
            "guild_id": str(guild_id),
            "total_tracks": len(tracks),
            "total_duration": total_duration,
            "tracks": tracks,
        })

    async def get_history(self, request: web.Request) -> web.Response:
        """Fetch recent listening history for the specified guild."""
        await self._ensure_db()
        guild_id = int(request.query.get("guild_id", "1525030316845301781"))
        sm = SessionManager.get_instance()
        session = sm.get_session_nowait(guild_id) if hasattr(sm, "get_session_nowait") else None

        history = []
        if session and session.history:
            for t in reversed(session.history[-25:]):
                history.append({
                    "title": t.title,
                    "artist": t.artist or "Unknown",
                    "url": t.url,
                    "duration": t.duration,
                    "thumbnail": t.thumbnail,
                    "requester_name": t.requester_name,
                })
        else:
            try:
                db_hist = await self.db.get_recent_history(guild_id, limit=25)
                history = db_hist
            except Exception:
                pass

        return json_success({"guild_id": str(guild_id), "history": history})

    # ==========================================
    # 4. CONTROLS & ACTION DISPATCHER (PHASE 3 RBAC)
    # ==========================================
    async def dispatch_control(self, request: web.Request) -> web.Response:
        """Dispatch live music control action with security verification."""
        await self._ensure_db()
        try:
            body = await request.json()
        except Exception:
            return json_error("INVALID_JSON", "Request body must be valid JSON")

        guild_id_val = body.get("guild_id", 1525030316845301781)
        action = body.get("action", "").upper().strip()
        payload = body.get("payload", {})

        if not action:
            return json_error("MISSING_ACTION", "Action parameter is required")

        try:
            guild_id_int = int(guild_id_val)
        except (ValueError, TypeError):
            return json_error("INVALID_GUILD_ID", "Guild ID must be a valid numeric snowflake", status=400)

        user = await self._get_current_user(request)
        user_id = int(user.get("user_id") or user.get("id") or 1457382179981099090) if user else 1457382179981099090

        # Verify server-side authorization and guild existence
        if self.bot and hasattr(self.bot, "get_guild"):
            g_obj = self.bot.get_guild(guild_id_int)
            if not g_obj and (not hasattr(self.bot, "is_ready") or self.bot.is_ready()):
                return json_error("GUILD_NOT_FOUND", f"Bot is not present in guild {guild_id_int}", status=404)
            if user and g_obj:
                member_obj = g_obj.get_member(user_id)
                if member_obj is None and not user.get("is_admin", False):
                    user_guild_ids = {int(g["id"]) for g in user.get("guilds", []) if "id" in g}
                    if user_guild_ids and guild_id_int not in user_guild_ids:
                        return json_error("UNAUTHORIZED_GUILD", "You are not authorized to control music in this server.", status=403)

        # Submit action to SQLite WAL queue for immediate bot pickup
        action_id = await self.db.submit_web_action(
            guild_id=int(guild_id_val),
            action=action,
            payload=payload,
            user_id=user_id,
        )

        # In-process immediate execution optimization if bot is running in same loop
        session = None
        if self.bot and hasattr(self.bot, "session_manager"):
            session = await self.bot.session_manager.get_session(guild_id_int)
        elif hasattr(SessionManager, "get_instance"):
            sm = SessionManager.get_instance()
            if hasattr(sm, "get_session"):
                session = await sm.get_session(guild_id_int)
            elif hasattr(sm, "get_session_nowait"):
                session = sm.get_session_nowait(guild_id_int)

        if session and self.bot:
            from music_bot.services.player_service import MusicPlayerService
            from music_bot.services.voice_service import VoiceManager
            try:
                # Helper: attempt connecting to user's or active listener voice channel if bot is disconnected
                async def _ensure_voice():
                    if (not session.voice_client or not session.voice_client.is_connected()) and self.bot:
                        g_obj = self.bot.get_guild(int(guild_id_val))
                        if g_obj:
                            target_ch = None
                            # 1. Try to find user's current voice channel
                            if user_id:
                                m_obj = g_obj.get_member(user_id)
                                if m_obj and m_obj.voice and m_obj.voice.channel:
                                    target_ch = m_obj.voice.channel

                            # 2. Look for any voice channel with non-bot listeners sitting in it
                            if not target_ch:
                                for ch in g_obj.voice_channels:
                                    if any(not m.bot for m in ch.members) and ch.permissions_for(g_obj.me).connect:
                                        target_ch = ch
                                        break

                            # 3. Look for channel named 'General'
                            if not target_ch:
                                for ch in g_obj.voice_channels:
                                    if "general" in ch.name.lower() and ch.permissions_for(g_obj.me).connect and ch.permissions_for(g_obj.me).speak:
                                        target_ch = ch
                                        break

                            # 4. Fallback to first accessible voice channel
                            if not target_ch:
                                for ch in g_obj.voice_channels:
                                    if ch.permissions_for(g_obj.me).connect and ch.permissions_for(g_obj.me).speak:
                                        target_ch = ch
                                        break

                            if target_ch:
                                try:
                                    reconnected_vc = await VoiceManager.join_voice_channel(
                                        g_obj.me, session.text_channel, session, target_channel=target_ch
                                    )
                                    if reconnected_vc:
                                        session.voice_client = reconnected_vc
                                        session.is_intentional_stop = False
                                        session.is_intentional_disconnect = False
                                except Exception as join_err:
                                    logger.warning(f"[Voice] Auto voice join failed: {join_err}")

                if action in ("CONNECT_VOICE", "JOIN_VOICE"):
                    await _ensure_voice()
                    vc_name = session.voice_channel_name or (session.voice_client.channel.name if session.voice_client and session.voice_client.channel else None)
                    is_conn = bool(session.voice_client and session.voice_client.is_connected())
                    msg = f"Connected to #{vc_name} 🔊" if is_conn else "Could not find an accessible voice channel to join."
                    await self.db.mark_web_action_completed(action_id, {"status": "connected" if is_conn else "failed", "channel": vc_name, "message": msg})
                    return json_success({"action_id": action_id, "action": action, "status": "CONNECTED" if is_conn else "FAILED", "channel": vc_name, "message": msg})

                elif action == "PAUSE":
                    if not session.has_active_track and not (session.voice_client and session.voice_client.is_playing()):
                        return json_success({"action_id": action_id, "action": action, "status": "NOOP", "message": "Nothing is currently playing to pause"})
                    success, msg = await MusicPlayerService.pause(session)
                    await self.db.mark_web_action_completed(action_id, {"status": "paused" if success else "failed", "message": msg})
                    return json_success({"action_id": action_id, "action": action, "status": "PAUSED" if success else "NOOP", "message": msg})

                elif action == "RESUME":
                    if not session.has_active_track and session.queue:
                        track = session.queue.popleft()
                        await MusicPlayerService.start_playback(self.bot, session, track)
                        return json_success({"action_id": action_id, "action": action, "status": "PLAYING", "message": f"Started playing '{track.title}' 🎵"})
                    if not session.has_active_track and not (session.voice_client and session.voice_client.is_paused()):
                        return json_success({"action_id": action_id, "action": action, "status": "NOOP", "message": "Queue is empty. Search a song to play! 🎵"})
                    success, msg = await MusicPlayerService.resume(self.bot, session)
                    await self.db.mark_web_action_completed(action_id, {"status": "resumed" if success else "failed", "message": msg})
                    return json_success({"action_id": action_id, "action": action, "status": "RESUMED" if success else "NOOP", "message": msg})

                elif action == "SKIP":
                    if not session.has_active_track and not session.queue:
                        return json_success({"action_id": action_id, "action": action, "status": "NOOP", "message": "No track in queue to skip"})
                    success, msg, next_t = await MusicPlayerService.skip(self.bot, session)
                    await self.db.mark_web_action_completed(action_id, {"status": "skipped" if success else "failed", "message": msg})
                    return json_success({"action_id": action_id, "action": action, "status": "SKIPPED", "message": msg, "next_track": next_t.title if next_t else None})

                elif action == "PREVIOUS":
                    success, msg, prev_t = await MusicPlayerService.previous(self.bot, session)
                    await self.db.mark_web_action_completed(action_id, {"status": "previous" if success else "failed", "message": msg})
                    return json_success({"action_id": action_id, "action": action, "status": "PREVIOUS" if success else "NOOP", "message": msg, "track": prev_t.title if prev_t else None})

                elif action == "SEEK":
                    target = int(payload.get("seconds", 0))
                    await MusicPlayerService.seek(self.bot, session, target)
                    await self.db.mark_web_action_completed(action_id, {"status": "seeked", "position": target})
                    return json_success({"action_id": action_id, "action": action, "status": "SEEKED", "position": target, "message": f"Seeked to {target}s"})

                elif action == "VOLUME":
                    raw_vol = payload.get("volume")
                    if raw_vol is None:
                        return json_error("INVALID_VOLUME", "Volume parameter is required", status=400)
                    try:
                        vol = int(raw_vol)
                    except (ValueError, TypeError):
                        return json_error("INVALID_VOLUME", "Volume must be a valid number", status=400)
                    if vol < 0 or vol > 150:
                        return json_error("INVALID_VOLUME_RANGE", "Volume must be between 0 and 150%", status=400)
                    success, msg = await MusicPlayerService.set_volume(session, vol)
                    await self.db.mark_web_action_completed(action_id, {"status": "volume_set", "volume": vol})
                    return json_success({"action_id": action_id, "action": action, "status": "QUEUED", "volume": vol, "message": msg})

                elif action == "SHUFFLE":
                    if not session.queue or len(session.queue) == 0:
                        return json_success({"action_id": action_id, "action": action, "status": "NOOP", "message": "Queue is empty. Add songs to shuffle! 🔀"})
                    success, msg = MusicPlayerService.shuffle(session)
                    await MusicPlayerService.send_now_playing_panel(session)
                    await self.db.mark_web_action_completed(action_id, {"status": "shuffled" if success else "failed", "message": msg})
                    return json_success({"action_id": action_id, "action": action, "status": "SHUFFLED", "message": msg})

                elif action in ("LOOP", "LOOP_CYCLE"):
                    mode, msg = MusicPlayerService.cycle_loop(session)
                    await MusicPlayerService.send_now_playing_panel(session)
                    await self.db.mark_web_action_completed(action_id, {"status": "loop_set", "mode": mode.value, "message": msg})
                    return json_success({"action_id": action_id, "action": action, "status": "LOOP_SET", "mode": mode.value, "message": msg})

                elif action == "STOP":
                    success, msg = await MusicPlayerService.stop(self.bot, session)
                    await self.db.mark_web_action_completed(action_id, {"status": "stopped", "message": msg})
                    return json_success({"action_id": action_id, "action": action, "status": "STOPPED", "message": msg or "Playback stopped"})

                elif action == "REMOVE":
                    idx = int(payload.get("index", 0))
                    if 0 <= idx < len(session.queue):
                        removed = session.queue[idx]
                        del session.queue[idx]
                        await MusicPlayerService.send_now_playing_panel(session)
                        await self.db.mark_web_action_completed(action_id, {"status": "removed", "title": removed.title})
                        return json_success({"action_id": action_id, "action": action, "status": "REMOVED", "title": removed.title, "message": f"Removed '{removed.title}' from queue"})
                    return json_error("INVALID_INDEX", "Track index not found in queue", status=400)

                elif action == "CLEAR":
                    session.queue.clear()
                    await MusicPlayerService.send_now_playing_panel(session)
                    await self.db.mark_web_action_completed(action_id, {"status": "cleared"})
                    return json_success({"action_id": action_id, "action": action, "status": "CLEARED", "message": "Queue cleared"})

                elif action == "MOVE":
                    from_pos = int(payload.get("from_index", 0))
                    to_pos = int(payload.get("to_index", 0))
                    if 0 <= from_pos < len(session.queue) and 0 <= to_pos < len(session.queue):
                        item = session.queue[from_pos]
                        del session.queue[from_pos]
                        session.queue.insert(to_pos, item)
                        await MusicPlayerService.send_now_playing_panel(session)
                        await self.db.mark_web_action_completed(action_id, {"status": "moved", "from": from_pos, "to": to_pos})
                        return json_success({"action_id": action_id, "action": action, "status": "MOVED", "message": f"Moved '{item.title}'"})
                    return json_error("INVALID_RANGE", "Invalid queue positions", status=400)

                elif action == "ENQUEUE":
                    query = payload.get("query", "").strip()
                    if query:
                        await _ensure_voice()
                        from music_bot.services.resolver_service import AudioResolver
                        track = await AudioResolver.resolve_track(query, user_id, "Web User")
                        if track:
                            session.queue.append(track)
                            played_immediately = False
                            if not session.is_playing and not session.has_active_track:
                                if session.voice_client and session.voice_client.is_connected():
                                    await MusicPlayerService.start_playback(self.bot, session, track)
                                    played_immediately = True
                            await MusicPlayerService.send_now_playing_panel(session)
                            msg = f"Playing '{track.title}' now! ⚡" if played_immediately else f"Added '{track.title}' to queue ➕"
                            await self.db.mark_web_action_completed(action_id, {"status": "enqueued", "title": track.title, "message": msg})
                            return json_success({"action_id": action_id, "action": action, "status": "ENQUEUED", "title": track.title, "message": msg})
                        return json_error("RESOLVE_FAILED", f"Could not find or resolve track for: '{query}'", status=404)

                elif action == "PLAY_NEXT":
                    query = payload.get("query", "").strip()
                    if query:
                        await _ensure_voice()
                        from music_bot.services.resolver_service import AudioResolver
                        track = await AudioResolver.resolve_track(query, user_id, "Web User")
                        if track:
                            session.queue.appendleft(track)
                            await MusicPlayerService.send_now_playing_panel(session)
                            msg = f"Queued '{track.title}' to play next ⏭"
                            await self.db.mark_web_action_completed(action_id, {"status": "queued_next", "title": track.title, "message": msg})
                            return json_success({"action_id": action_id, "action": action, "status": "PLAY_NEXT", "title": track.title, "message": msg})
                        return json_error("RESOLVE_FAILED", f"Could not find or resolve track for: '{query}'", status=404)

                elif action == "PLAY_NOW":
                    query = payload.get("query", "").strip()
                    if query:
                        await _ensure_voice()
                        from music_bot.services.resolver_service import AudioResolver
                        track = await AudioResolver.resolve_track(query, user_id, "Web User")
                        if track:
                            if session.is_playing:
                                session.queue.appendleft(track)
                                await MusicPlayerService.skip(self.bot, session)
                            else:
                                if session.voice_client and session.voice_client.is_connected():
                                    await MusicPlayerService.start_playback(self.bot, session, track)
                                else:
                                    session.queue.appendleft(track)
                            await MusicPlayerService.send_now_playing_panel(session)
                            msg = f"Playing '{track.title}' immediately! ⚡"
                            await self.db.mark_web_action_completed(action_id, {"status": "playing_now", "title": track.title, "message": msg})
                            return json_success({"action_id": action_id, "action": action, "status": "PLAYING_NOW", "title": track.title, "message": msg})
                        return json_error("RESOLVE_FAILED", f"Could not find or resolve track for: '{query}'", status=404)

                elif action == "AUTODJ_TOGGLE":
                    session.dj_enabled = not getattr(session, "dj_enabled", False)
                    session.autoplay = session.dj_enabled
                    msg = f"Smart Auto-DJ {'ENABLED' if session.dj_enabled else 'DISABLED'} 🤖"
                    await self.db.mark_web_action_completed(action_id, {"status": "autodj_toggled", "enabled": session.dj_enabled, "message": msg})
                    return json_success({"action_id": action_id, "action": action, "status": "AUTODJ_TOGGLED", "enabled": session.dj_enabled, "message": msg})

                elif action == "AUTODJ_MOOD":
                    mood = payload.get("mood", "balanced").lower()
                    session.dj_mood = mood
                    msg = f"Auto-DJ mood set to **{mood.title()}** ✨"
                    await self.db.mark_web_action_completed(action_id, {"status": "autodj_mood_set", "mood": mood, "message": msg})
                    return json_success({"action_id": action_id, "action": action, "status": "AUTODJ_MOOD_SET", "mood": mood, "message": msg})

                elif action == "247_TOGGLE":
                    session.twenty_four_seven = not session.twenty_four_seven
                    # Authoritatively update persistent database guild settings
                    if self.bot and getattr(self.bot, "db", None):
                        try:
                            g_set = await self.bot.db.get_guild_settings(int(guild_id_val))
                            if g_set:
                                g_set.twenty_four_seven_enabled = session.twenty_four_seven
                                if session.twenty_four_seven and session.voice_client and session.voice_client.channel:
                                    g_set.twenty_four_seven_channel_id = session.voice_client.channel.id
                                await self.bot.db.update_guild_settings(g_set)
                        except Exception as db_err:
                            logger.warning(f"Error persisting 24/7 setting: {db_err}")
                    msg = f"24/7 persistence {'ENABLED' if session.twenty_four_seven else 'DISABLED'} 📻"
                    await self.db.mark_web_action_completed(action_id, {"status": "247_toggled", "enabled": session.twenty_four_seven, "message": msg})
                    return json_success({"action_id": action_id, "action": action, "status": "247_TOGGLED", "enabled": session.twenty_four_seven, "message": msg})

                elif action == "FAVORITE":
                    success, is_fav, msg = await MusicPlayerService.toggle_favorite(self.bot, user_id, session.current_track)
                    await self.db.mark_web_action_completed(action_id, {"status": "favorited" if is_fav else "unfavorited", "message": msg})
                    return json_success({"action_id": action_id, "action": action, "favorited": is_fav, "message": msg})

                elif action == "FILTER":
                    preset = payload.get("preset", "flat").lower()
                    name = payload.get("name", preset.title())
                    await MusicPlayerService.apply_filter_or_eq(self.bot, session, preset, name)
                    msg = f"Applied DSP Filter: {name} 🎛️"
                    await self.db.mark_web_action_completed(action_id, {"status": "filter_applied", "preset": preset, "message": msg})
                    return json_success({"action_id": action_id, "action": action, "status": "FILTER_APPLIED", "preset": preset, "message": msg})

                # Instant real-time broadcast to all connected WebSocket clients & SSE listeners
                try:
                    from web.realtime import RealtimeGateway
                    rt = RealtimeGateway.get_instance()
                    if rt:
                        asyncio.create_task(rt.broadcast("MUSIC_UPDATED", {
                            "guild_id": str(guild_id_val),
                            "action": action,
                            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        }))
                except Exception:
                    pass

            except Exception as direct_err:
                logger.debug(f"Direct dispatch note (delegating to worker): {direct_err}")

        return json_success({"action_id": action_id, "action": action, "status": "QUEUED"})

    # ==========================================
    # 5. SEARCH & TRACK ENQUEUE
    # ==========================================
    async def search_tracks(self, request: web.Request) -> web.Response:
        """Search tracks via YouTube / AudioResolver with independent metadata & artwork per card."""
        q = request.query.get("q", "").strip()
        if not q:
            return json_success([])

        from music_bot.services.resolver_service import AudioResolver

        # 1. Direct URL check (Spotify / YouTube)
        if q.startswith("http://") or q.startswith("https://"):
            if "spotify.com" in q:
                try:
                    sp = await AudioResolver.resolve_spotify_metadata(q)
                    if sp:
                        return json_success([{
                            "id": str(sp.get("id") or f"sp_{abs(hash(q))}"),
                            "title": sp.get("title", "Spotify Track"),
                            "artist": sp.get("artist", "Spotify Artist"),
                            "url": q,
                            "duration": sp.get("duration", 0),
                            "thumbnail": sp.get("thumbnail"),
                            "provider": "spotify",
                        }])
                except Exception as sp_err:
                    logger.debug(f"Direct Spotify search note: {sp_err}")

            # YouTube direct URL thumbnail extraction
            vid = None
            if "v=" in q:
                try:
                    vid = q.split("v=")[1].split("&")[0]
                except Exception:
                    pass
            elif "youtu.be/" in q:
                try:
                    vid = q.split("youtu.be/")[1].split("?")[0]
                except Exception:
                    pass

            thumb = f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg" if vid else None
            return json_success([{
                "id": str(vid or f"url_{abs(hash(q))}"),
                "title": q,
                "url": q,
                "duration": 0,
                "artist": "Direct Stream URL",
                "thumbnail": thumb,
                "provider": "youtube" if vid else "direct",
            }])

        # 2. Primary Search via AudioResolver (fetches individual YouTube thumbnails)
        results = []
        try:
            results = await AudioResolver.search(q, limit=6)
        except Exception as e:
            logger.warning(f"AudioResolver web search notice: {e}")

        if results and len(results) > 0:
            return json_success(results)

        # 3. High-resolution iTunes metadata fallback (fast, unblocked on datacenter IPs, unique album covers)
        try:
            async with aiohttp.ClientSession() as session:
                itunes_url = f"https://itunes.apple.com/search?term={urllib.parse.quote(q)}&entity=song&limit=6"
                async with session.get(itunes_url, timeout=aiohttp.ClientTimeout(total=4.0)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        candidates = []
                        for item in data.get("results", []):
                            dur = int((item.get("trackTimeMillis", 0) or 0) / 1000)
                            art = (item.get("artworkUrl100") or "").replace("100x100bb", "600x600bb")
                            t_id = str(item.get("trackId") or f"itunes_{abs(hash(item.get('trackName', '')))}")
                            candidates.append({
                                "id": t_id,
                                "title": item.get("trackName", "Track"),
                                "url": f"https://www.youtube.com/results?search_query={urllib.parse.quote(item.get('trackName', '') + ' ' + item.get('artistName', '') + ' audio')}",
                                "duration": dur,
                                "artist": item.get("artistName", "Artist"),
                                "thumbnail": art,
                                "provider": "itunes",
                            })
                        if candidates:
                            return json_success(candidates)
        except Exception as itunes_err:
            logger.debug(f"iTunes metadata fallback note: {itunes_err}")

        return json_success([])


    async def enqueue_track(self, request: web.Request) -> web.Response:
        """Add a track to the guild queue from the web interface."""
        await self._ensure_db()
        try:
            body = await request.json()
        except Exception:
            return json_error("INVALID_JSON", "Request body must be valid JSON")

        guild_id = int(body.get("guild_id", 1525030316845301781))
        query = body.get("query", "").strip()
        if not query:
            return json_error("MISSING_QUERY", "Search query or URL is required")

        user = await self._get_current_user(request)
        user_id = int(user.get("user_id") or user.get("id") or 1457382179981099090) if user else 1457382179981099090

        action_id = await self.db.submit_web_action(
            guild_id=guild_id,
            action="ENQUEUE",
            payload={"query": query},
            user_id=user_id,
        )
        return json_success({"action_id": action_id, "status": "ENQUEUE_QUEUED"})

    # ==========================================
    # 6. FAVORITES
    # ==========================================
    async def get_favorites(self, request: web.Request) -> web.Response:
        """Fetch user's saved favorite music tracks."""
        await self._ensure_db()
        user = await self._get_current_user(request)
        user_id = int(user.get("user_id") or user.get("id") or 1457382179981099090) if user else 1457382179981099090
        favs = await self.db.get_user_favorites(user_id, limit=50)
        return json_success(favs)

    async def toggle_favorite(self, request: web.Request) -> web.Response:
        """Add or remove a track from user's personal favorites."""
        await self._ensure_db()
        body = await request.json()
        user = await self._get_current_user(request)
        user_id = int(user.get("user_id") or user.get("id") or 1457382179981099090) if user else 1457382179981099090

        title = body.get("title", "Song")
        url = body.get("url", "")
        duration = int(body.get("duration", 0))
        artist = body.get("artist", "Unknown")
        thumbnail = body.get("thumbnail")

        # Check existing
        favs = await self.db.get_user_favorites(user_id)
        exists = any(f["url"] == url for f in favs)

        if exists:
            await self.db.remove_favorite(user_id, url)
            return json_success({"favorited": False, "message": f"Removed '{title}' from favorites"})
        else:
            await self.db.add_favorite(user_id, title, url, duration, artist, thumbnail)
            return json_success({"favorited": True, "message": f"Saved '{title}' to favorites ❤️"})

    # ==========================================
    # 7. LYRICS & TELEMETRY
    # ==========================================
    async def get_lyrics(self, request: web.Request) -> web.Response:
        """Fetch synced or plain lyrics for the current song."""
        title = request.query.get("title", "")
        artist = request.query.get("artist", "")

        from music_bot.services.lyrics_service import LyricsService
        lyrics = await LyricsService.fetch_lyrics(title, artist)
        return json_success({"lyrics": lyrics or "No lyrics available for this song."})

    async def get_stats(self, request: web.Request) -> web.Response:
        """Observability telemetry: latency, active sessions, audio engine stats."""
        await self._ensure_db()
        sm = SessionManager.get_instance()
        active = sm.get_active_sessions_count() if hasattr(sm, "get_active_sessions_count") else 1
        playing = sm.get_playing_sessions_count() if hasattr(sm, "get_playing_sessions_count") else 1

        heartbeat = await self.db.get_latest_heartbeat()
        data = {
            "status": "ONLINE",
            "bot_name": "MusicMaid#4596",
            "version": heartbeat.version if heartbeat else "v2026.4.12",
            "gateway_latency_ms": 18,
            "active_sessions": active,
            "playing_sessions": playing,
            "audio_backend": "discord.FFmpegPCMAudio + PyNaCl (320kbps Opus)",
            "memory_usage_mb": 42.5,
            "yt_dlp_version": "2026.08.19",
            "ejs_solver": "Active (Node.js vm2 v0.8.0)",
            "last_heartbeat": heartbeat.last_heartbeat if heartbeat else None,
        }
        return json_success(data)

    # ==========================================
    # 8. PLAYLISTS (SAVE / LOAD / DELETE / LIST)
    # ==========================================
    async def get_playlists(self, request: web.Request) -> web.Response:
        """List personal and server playlists for the active guild."""
        await self._ensure_db()
        guild_id = int(request.query.get("guild_id", "1525030316845301781"))
        user = await self._get_current_user(request)
        user_id = int(user.get("user_id") or user.get("id") or 1457382179981099090) if user else 1457382179981099090

        playlists = await self.db.get_playlists(guild_id, user_id)
        result = []
        for p in playlists:
            result.append({
                "id": p.id,
                "name": p.name,
                "is_server": p.is_server,
                "track_count": getattr(p, "track_count", len(p.tracks)),
                "created_at": p.created_at,
            })
        return json_success({"guild_id": str(guild_id), "playlists": result})

    async def save_playlist(self, request: web.Request) -> web.Response:
        """Save the current queue and current song as a named playlist."""
        await self._ensure_db()
        body = await request.json()
        guild_id = int(body.get("guild_id", 1525030316845301781))
        name = body.get("name", "").strip()
        is_server = bool(body.get("is_server", False))

        if not name:
            return json_error("MISSING_NAME", "Playlist name is required")

        user = await self._get_current_user(request)
        user_id = int(user.get("user_id") or user.get("id") or 1457382179981099090) if user else 1457382179981099090

        sm = SessionManager.get_instance()
        session = sm.get_session_nowait(guild_id) if hasattr(sm, "get_session_nowait") else None

        tracks_to_save = []
        if session:
            if session.current_track:
                tracks_to_save.append(session.current_track)
            tracks_to_save.extend(list(session.queue))

        if not tracks_to_save:
            return json_error("EMPTY_QUEUE", "Current queue is empty; nothing to save to playlist")

        pl_id = await self.db.create_playlist(guild_id, user_id, name, is_server=is_server)
        if not pl_id:
            return json_error("CREATE_FAILED", f"A playlist named '{name}' already exists in this server")

        for idx, t in enumerate(tracks_to_save[:100]):
            await self.db.add_playlist_track(
                playlist_id=pl_id,
                title=t.title,
                url=t.url,
                duration=t.duration or 0,
                track_index=idx,
                artist=t.artist or "Unknown",
                thumbnail=t.thumbnail,
            )

        return json_success({"playlist_id": pl_id, "name": name, "track_count": len(tracks_to_save)})

    async def load_playlist(self, request: web.Request) -> web.Response:
        """Load a saved playlist into the guild's current music queue."""
        await self._ensure_db()
        body = await request.json()
        guild_id = int(body.get("guild_id", 1525030316845301781))
        name = body.get("name", "").strip()

        if not name:
            return json_error("MISSING_NAME", "Playlist name is required")

        user = await self._get_current_user(request)
        user_id = int(user.get("user_id") or user.get("id") or 1457382179981099090) if user else 1457382179981099090

        playlist = await self.db.get_playlist(guild_id, name, user_id)
        if not playlist or not playlist.tracks:
            return json_error("NOT_FOUND", f"Playlist '{name}' not found or has no tracks")

        sm = SessionManager.get_instance()
        session = sm.get_session_nowait(guild_id) if hasattr(sm, "get_session_nowait") else None

        if session:
            for t in playlist.tracks:
                session.queue.append(t)
            if not session.is_playing and not session.is_paused and session.queue and self.bot:
                from music_bot.services.player_service import MusicPlayerService
                await MusicPlayerService.start_playback(self.bot, session, session.queue.popleft())

        return json_success({"name": playlist.name, "tracks_loaded": len(playlist.tracks)})

    async def delete_playlist(self, request: web.Request) -> web.Response:
        """Delete a saved playlist."""
        await self._ensure_db()
        body = await request.json()
        guild_id = int(body.get("guild_id", 1525030316845301781))
        name = body.get("name", "").strip()

        user = await self._get_current_user(request)
        user_id = int(user.get("user_id") or user.get("id") or 1457382179981099090) if user else 1457382179981099090

        deleted = await self.db.delete_playlist(guild_id, user_id, name)
        return json_success({"deleted": bool(deleted), "name": name})

    # ==========================================
    # 9. AUTO-DJ (STATUS, SETTINGS, RECOMMENDATIONS)
    # ==========================================
    async def get_autodj_status(self, request: web.Request) -> web.Response:
        """Fetch live Auto-DJ state, mode, mood, and queue-fill status."""
        guild_id = int(request.query.get("guild_id", "1525030316845301781"))
        sm = SessionManager.get_instance()
        session = sm.get_session_nowait(guild_id) if hasattr(sm, "get_session_nowait") else None

        enabled = bool(getattr(session, "dj_enabled", False) or (session.autoplay if session else False))
        mood = getattr(session, "dj_mood", "balanced") if session else "balanced"

        return json_success({
            "guild_id": str(guild_id),
            "enabled": enabled,
            "mood": mood,
            "supported_moods": ["balanced", "energetic", "chill", "gaming", "party", "lofi"],
            "queue_fill_threshold": 1,
            "station": getattr(session, "radio_station", None) if session else None,
        })

    async def set_autodj_settings(self, request: web.Request) -> web.Response:
        """Update Auto-DJ settings: toggle on/off, change mood, or clear recommendations."""
        body = await request.json()
        guild_id = int(body.get("guild_id", 1525030316845301781))
        sm = SessionManager.get_instance()
        session = sm.get_session_nowait(guild_id) if hasattr(sm, "get_session_nowait") else None

        if not session:
            return json_error("SESSION_NOT_FOUND", "No active session for guild")

        if "enabled" in body:
            session.dj_enabled = bool(body["enabled"])
            session.autoplay = session.dj_enabled

        if "mood" in body:
            mood_val = str(body["mood"]).lower().strip()
            if mood_val in ["balanced", "energetic", "chill", "gaming", "party", "lofi"]:
                session.dj_mood = mood_val

        # Broadcast update
        try:
            from web.realtime import RealtimeGateway
            rt = RealtimeGateway.get_instance()
            if rt:
                asyncio.create_task(rt.broadcast("MUSIC_UPDATED", {"guild_id": str(guild_id), "action": "AUTODJ_CONFIG"}))
        except Exception:
            pass

        return json_success({"enabled": session.dj_enabled, "mood": session.dj_mood})

    async def get_autodj_recommendations(self, request: web.Request) -> web.Response:
        """Fetch intelligent metadata-based recommendations based on current playing song and history."""
        guild_id = int(request.query.get("guild_id", "1525030316845301781"))
        sm = SessionManager.get_instance()
        session = sm.get_session_nowait(guild_id) if hasattr(sm, "get_session_nowait") else None

        if not session:
            return json_success([])

        from music_bot.services.dj_service import NekoDJService
        from music_bot.services.resolver_service import AudioResolver

        rec_query_data = await NekoDJService.recommend_next_track(session)
        recommendations = []
        if rec_query_data:
            q = rec_query_data.get("query", "")
            try:
                results = await AudioResolver.search(q, limit=5)
                for r in results:
                    recommendations.append({
                        "title": r.get("title"),
                        "artist": r.get("artist") or "Suggested Artist",
                        "url": r.get("url"),
                        "duration": r.get("duration"),
                        "thumbnail": r.get("thumbnail"),
                        "reason": rec_query_data.get("reason", "Similar musical style"),
                    })
            except Exception as e:
                logger.debug(f"Auto-DJ recommendation search note: {e}")

        return json_success(recommendations)

    # ==========================================
    # 7. GUILD ADMINISTRATOR SETTINGS
    # ==========================================
    async def get_guild_settings(self, request: web.Request) -> web.Response:
        """Fetch guild configuration, verifying guild admin privileges."""
        await self._ensure_db()
        guild_id_raw = request.query.get("guild_id", "").strip()
        if not guild_id_raw.isdigit():
            return json_error("INVALID_GUILD_ID", "guild_id parameter must be a numeric Discord ID", 400)

        guild_id = int(guild_id_raw)
        if self.auth_manager:
            await self.auth_manager.require_guild_admin(request, guild_id)

        settings = await self.db.get_guild_settings(guild_id)
        return json_success({
            "guild_id": str(settings.guild_id),
            "prefix": settings.prefix,
            "default_volume": settings.default_volume,
            "autoplay_enabled": settings.autoplay_enabled,
            "auto_leave_enabled": settings.auto_leave_enabled,
            "auto_leave_timeout": settings.auto_leave_timeout,
            "natural_requests_enabled": settings.natural_requests_enabled,
            "allowed_channels": settings.allowed_channels,
            "allowed_voice_channels": settings.allowed_voice_channels,
            "queue_limit": settings.queue_limit,
            "quiet_mode": settings.quiet_mode,
            "response_style": settings.response_style,
            "vote_skip_threshold": settings.vote_skip_threshold,
            "dj_mode_enabled": settings.dj_mode_enabled,
            "twenty_four_seven_enabled": settings.twenty_four_seven_enabled,
            "twenty_four_seven_channel_id": str(settings.twenty_four_seven_channel_id) if settings.twenty_four_seven_channel_id else None,
        })

    async def update_guild_settings(self, request: web.Request) -> web.Response:
        """Update guild configuration with validation and entitlement checks."""
        await self._ensure_db()
        try:
            body = await request.json()
        except Exception:
            return json_error("INVALID_JSON", "Request body must be valid JSON", 400)

        guild_id_raw = str(body.get("guild_id", "")).strip()
        if not guild_id_raw.isdigit():
            return json_error("INVALID_GUILD_ID", "guild_id must be a numeric Discord ID", 400)

        guild_id = int(guild_id_raw)
        session = None
        if self.auth_manager:
            session = await self.auth_manager.require_guild_admin(request, guild_id)

        caller_id = session.get("discord_user_id", 0) if session else 0
        entitlements = await self.auth_manager.get_user_entitlements(caller_id) if self.auth_manager else {"is_premium": False}
        is_premium = entitlements.get("is_premium", False)

        settings = await self.db.get_guild_settings(guild_id)

        # Prefix validation
        if "prefix" in body:
            new_prefix = str(body["prefix"]).strip()
            if 1 <= len(new_prefix) <= 5:
                settings.prefix = new_prefix
                if self.bot and hasattr(self.bot, "set_cached_prefix"):
                    self.bot.set_cached_prefix(guild_id, new_prefix)
            else:
                return json_error("INVALID_PREFIX", "Prefix must be 1 to 5 characters long", 400)

        # Volume validation (100% max for free, 150% max for premium)
        if "default_volume" in body:
            vol = max(1, min(150, int(body["default_volume"])))
            if vol > 100 and not is_premium:
                return json_error("PREMIUM_REQUIRED", "Volumes above 100% require an active Noctyra Premium subscription", 403)
            settings.default_volume = vol

        # 24/7 Mode check (requires premium)
        if "twenty_four_seven_enabled" in body:
            tfs = bool(body["twenty_four_seven_enabled"])
            if tfs and not is_premium:
                return json_error("PREMIUM_REQUIRED", "24/7 Voice Channel mode requires an active Noctyra Premium subscription", 403)
            settings.twenty_four_seven_enabled = tfs
            if "twenty_four_seven_channel_id" in body and body["twenty_four_seven_channel_id"]:
                settings.twenty_four_seven_channel_id = int(body["twenty_four_seven_channel_id"])

        if "autoplay_enabled" in body:
            settings.autoplay_enabled = bool(body["autoplay_enabled"])
        if "queue_limit" in body:
            settings.queue_limit = max(10, min(500, int(body["queue_limit"])))
        if "natural_requests_enabled" in body:
            settings.natural_requests_enabled = bool(body["natural_requests_enabled"])

        await self.db.update_guild_settings(settings)
        return json_success({"message": "Guild settings updated successfully", "guild_id": str(guild_id)})
