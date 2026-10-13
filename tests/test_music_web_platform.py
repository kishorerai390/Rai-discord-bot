"""
Integration and Unit Tests for Raivora Music Web Platform (Phase 2 & Phase 3).
Validates music API routes, session polling, queue management, control dispatch, and action lifecycles.
"""

import asyncio
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase

from web.server import RaiCommunityOSServer
from web.music_api import MusicApiRouter
from music_bot.database.db import MusicDatabase
from music_bot.services.session_service import GuildMusicSession, PlaybackState, LoopMode, SessionManager
from music_bot.database.models import QueuedTrack


def make_track(title: str = "Test Track", duration: int = 210) -> QueuedTrack:
    return QueuedTrack(
        title=title,
        url="https://youtube.com/watch?v=mocktrack",
        stream_url="https://mock.stream/audio.mp3",
        duration=duration,
        artist="Test Artist",
        thumbnail="https://mock.thumb/art.jpg",
        requester_id=1457382179981099090,
        requester_name="RaiTester",
    )


class TestRaivoraMusicWebPlatform(AioHTTPTestCase):
    """Test suite for the Raivora Music Web Platform."""

    async def get_application(self) -> web.Application:
        # Mock database and bot
        self.mock_db = MagicMock()
        self.mock_db.is_connected = True
        self.mock_db.connect = AsyncMock()
        self.mock_db.close = AsyncMock()
        self.mock_db.fetch_pending_sync_events = AsyncMock(return_value=[])

        self.mock_bot = MagicMock()
        self.mock_bot.db = self.mock_db
        self.mock_bot.latency = 0.018

        self.rai_server = RaiCommunityOSServer(bot=self.mock_bot, db=self.mock_db, port=8199)
        app = web.Application()
        self.rai_server.setup_routes(app)
        return app

    async def test_01_music_guilds_endpoint(self):
        """1. GET /api/music/guilds returns accessible guilds list."""
        resp = await self.client.get("/api/music/guilds")
        assert resp.status == 200
        json_data = await resp.json()
        assert json_data["success"] is True
        assert "guilds" in json_data["data"]
        assert len(json_data["data"]["guilds"]) > 0
        apex_guild = [g for g in json_data["data"]["guilds"] if g["id"] == "1525030316845301781"][0]
        assert apex_guild["name"] == "THOR APEX ⚡"

    async def test_02_music_session_active_state(self):
        """2. GET /api/music/session returns real-time track metadata and progress."""
        sm = SessionManager.get_instance()
        test_session = sm.get_session_nowait(1525030316845301781)
        if not test_session:
            test_session = GuildMusicSession(guild_id=1525030316845301781)
            sm._sessions[1525030316845301781] = test_session

        t = make_track("Cyberpunk Symphony", 180)
        test_session.current_track = t
        test_session.state = PlaybackState.PLAYING
        test_session.track_start_time = 100.0
        test_session.volume = 65

        mock_vc = MagicMock()
        mock_vc.is_playing.return_value = True
        mock_vc.is_paused.return_value = False
        mock_vc.channel.id = 999
        mock_vc.channel.name = "Fun Time"
        test_session.voice_client = mock_vc

        resp = await self.client.get("/api/music/session?guild_id=1525030316845301781")
        assert resp.status == 200
        json_data = await resp.json()
        assert json_data["success"] is True
        d = json_data["data"]
        assert d["is_playing"] is True
        assert d["current_track"]["title"] == "Cyberpunk Symphony"
        assert d["volume"] == 65
        assert d["voice_channel_name"] == "Fun Time"

    async def test_03_music_queue_listing(self):
        """3. GET /api/music/queue returns queued tracks and total duration."""
        sm = SessionManager.get_instance()
        test_session = sm.get_session_nowait(1525030316845301781)
        test_session.queue.clear()
        test_session.queue.append(make_track("Track 1", 120))
        test_session.queue.append(make_track("Track 2", 180))

        resp = await self.client.get("/api/music/queue?guild_id=1525030316845301781")
        assert resp.status == 200
        json_data = await resp.json()
        assert json_data["success"] is True
        d = json_data["data"]
        assert d["total_tracks"] == 2
        assert d["total_duration"] == 300
        assert d["tracks"][0]["title"] == "Track 1"
        assert d["tracks"][1]["title"] == "Track 2"

    async def test_04_music_control_dispatch(self):
        """4. POST /api/music/control submits actions to the WAL queue."""
        payload = {
            "guild_id": 1525030316845301781,
            "action": "VOLUME",
            "payload": {"volume": 50},
        }
        resp = await self.client.post("/api/music/control", json=payload)
        assert resp.status == 200
        json_data = await resp.json()
        assert json_data["success"] is True
        assert json_data["data"]["action"] == "VOLUME"
        assert json_data["data"]["status"] == "QUEUED"

    async def test_05_music_enqueue_endpoint(self):
        """5. POST /api/music/enqueue queues search requests."""
        payload = {
            "guild_id": 1525030316845301781,
            "query": "Kaappaan Hey Amigo",
        }
        resp = await self.client.post("/api/music/enqueue", json=payload)
        assert resp.status == 200
        json_data = await resp.json()
        assert json_data["success"] is True
        assert json_data["data"]["status"] == "ENQUEUE_QUEUED"

    async def test_06_music_stats_telemetry(self):
        """6. GET /api/music/stats returns health metrics."""
        resp = await self.client.get("/api/music/stats")
        assert resp.status == 200
        json_data = await resp.json()
        assert json_data["success"] is True
        d = json_data["data"]
        assert d["status"] == "ONLINE"
        assert "gateway_latency_ms" in d
        assert "yt_dlp_version" in d

    async def test_07_music_favorites_toggle(self):
        """7. POST /api/music/favorites/toggle adds and removes favorites."""
        track_payload = {
            "title": "Favorite Song",
            "url": "https://yt/fav",
            "duration": 200,
            "artist": "Artist",
        }
        resp = await self.client.post("/api/music/favorites/toggle", json=track_payload)
        assert resp.status == 200
        json_data = await resp.json()
        assert json_data["success"] is True
        assert "favorited" in json_data["data"]

    async def test_08_session_permissions_and_rbac(self):
        """8. GET /api/music/session returns permission-aware control metadata."""
        resp = await self.client.get("/api/music/session?guild_id=1525030316845301781")
        assert resp.status == 200
        json_data = await resp.json()
        assert json_data["success"] is True
        assert "permissions" in json_data["data"]
        perms = json_data["data"]["permissions"]
        assert "can_control" in perms
        assert "is_admin" in perms
        assert "is_staff" in perms

    async def test_09_realtime_music_session_broadcasting(self):
        """9. RealtimeGateway collects active music sessions with type 'music'."""
        sm = SessionManager.get_instance()
        test_session = sm.get_session_nowait(1525030316845301781)
        if not test_session:
            test_session = GuildMusicSession(guild_id=1525030316845301781)
            sm._sessions[1525030316845301781] = test_session

        test_session.current_track = make_track("Lossless Live Track", 240)
        test_session.state = PlaybackState.PLAYING

        mock_vc = MagicMock()
        mock_vc.is_playing.return_value = True
        mock_vc.channel.name = "Live Stage"
        mock_vc.channel.members = [MagicMock(bot=False)]
        test_session.voice_client = mock_vc

        live_sessions = await self.rai_server.realtime_gateway.collect_live_sessions()
        music_sessions = [s for s in live_sessions if s.get("type") == "music"]
        assert len(music_sessions) > 0
        assert music_sessions[0]["title"] == "Lossless Live Track"
        assert music_sessions[0]["destination"] == "/music"

    async def test_10_authoritative_pause_resume_dispatch(self):
        """10. In-process dispatch executes authoritative MusicPlayerService methods."""
        from music_bot.services.player_service import MusicPlayerService

        sm = SessionManager.get_instance()
        test_session = sm.get_session_nowait(1525030316845301781)
        test_session.current_track = make_track("Track For Pause", 180)
        test_session.state = PlaybackState.PLAYING

        with patch.object(MusicPlayerService, "pause", new_callable=AsyncMock) as mock_pause, \
             patch.object(MusicPlayerService, "resume", new_callable=AsyncMock) as mock_resume:
            mock_pause.return_value = (True, "Playback paused.")
            mock_resume.return_value = (True, "Playback resumed.")

            resp = await self.client.post("/api/music/control", json={
                "guild_id": 1525030316845301781,
                "action": "PAUSE"
            })
            assert resp.status == 200
            mock_pause.assert_called_once()

            resp = await self.client.post("/api/music/control", json={
                "guild_id": 1525030316845301781,
                "action": "RESUME"
            })
            assert resp.status == 200
            mock_resume.assert_called_once()

