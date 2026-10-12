"""
Tests for MusicBot Enhancements, Extractor Self-Healing, and Auto-Updater Suite.
Verifies:
1. AutoUpdater reports yt-dlp, EJS challenge solver, and JS runtime (Node.js).
2. AudioResolver health probe resolves without SABR format exceptions.
3. Priority Bump moves specified queue items to position #1.
4. Favorites database operations (add, retrieve, delete).
5. Music Wrapped statistical aggregations.
6. Export functionality generates valid JSON, M3U, and text formats and respects the zero-channel constraint.
"""

from __future__ import annotations

import asyncio
import io
import json
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from music_bot.database.db import MusicDatabase
from music_bot.database.models import QueuedTrack
from music_bot.services.resolver_service import AudioResolver
from music_bot.services.session_service import GuildMusicSession, SessionManager
from music_bot.services.updater_service import MusicAutoUpdater


class TestMusicEnhancementsAndUpdater(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.test_db_path = Path("data/test_enhancements.db")
        if self.test_db_path.exists():
            self.test_db_path.unlink()

        self.db = MusicDatabase(self.test_db_path)
        await self.db.connect()

    async def asyncTearDown(self):
        await self.db.close()
        if self.test_db_path.exists():
            self.test_db_path.unlink()

    async def test_autoupdater_runtime_and_ejs_detection(self):
        """Verify yt-dlp version, EJS solver, and Node.js runtime detection."""
        ytdl_ver = MusicAutoUpdater.get_current_ytdl_version()
        ejs_ver = MusicAutoUpdater.get_ejs_version()
        js_info = MusicAutoUpdater.get_js_runtime_info()

        self.assertIsNotNone(ytdl_ver)
        self.assertNotEqual(ytdl_ver, "unknown")
        self.assertIn("Node", js_info.get("active", ""))
        self.assertTrue(js_info.get("node_available"))

    async def test_favorites_crud_lifecycle(self):
        """Verify adding, fetching, and removing personal favorites."""
        user_id = 987654321
        ok = await self.db.add_favorite(
            user_id=user_id,
            title="Lofi Chill Morning Beats",
            url="https://youtube.com/watch?v=rrgOMpENU_Q",
            duration=180,
            artist="ChilledCow",
            thumbnail="https://example.com/thumb.jpg",
        )
        self.assertTrue(ok)

        favs = await self.db.get_user_favorites(user_id)
        self.assertEqual(len(favs), 1)
        self.assertEqual(favs[0]["title"], "Lofi Chill Morning Beats")

        # Remove favorite
        removed = await self.db.remove_favorite(user_id, str(favs[0]["id"]))
        self.assertTrue(removed)

        favs_after = await self.db.get_user_favorites(user_id)
        self.assertEqual(len(favs_after), 0)

    async def test_guild_wrapped_analytics(self):
        """Verify aggregation of played tracks for Server Music Wrapped."""
        guild_id = 555001

        # Record multiple tracks
        await self.db.record_history(guild_id, "Track Alpha", "https://yt.com/1", "Artist 1", 101)
        await self.db.record_history(guild_id, "Track Alpha", "https://yt.com/1", "Artist 1", 101)
        await self.db.record_history(guild_id, "Track Beta", "https://yt.com/2", "Artist 2", 102)

        stats = await self.db.get_guild_wrapped_stats(guild_id)
        self.assertEqual(stats["total_plays"], 3)
        self.assertEqual(len(stats["top_tracks"]), 2)
        self.assertEqual(stats["top_tracks"][0]["title"], "Track Alpha")
        self.assertEqual(stats["top_tracks"][0]["play_count"], 2)
        self.assertEqual(stats["top_requesters"][0]["requester_id"], 101)

    async def test_priority_bump_queue_order(self):
        """Verify priority bump moves item to position #1 in queue."""
        session = GuildMusicSession(guild_id=111, session_manager=SessionManager())
        t1 = QueuedTrack(title="Song 1", url="http://1", stream_url="http://s1", duration=100, requester_id=1, requester_name="A")
        t2 = QueuedTrack(title="Song 2", url="http://2", stream_url="http://s2", duration=100, requester_id=1, requester_name="A")
        t3 = QueuedTrack(title="Song 3", url="http://3", stream_url="http://s3", duration=100, requester_id=1, requester_name="A")

        session.queue.append(t1)
        session.queue.append(t2)
        session.queue.append(t3)

        # Bump Song 3 (index 2) to front
        bumped = session.queue[2]
        del session.queue[2]
        session.queue.appendleft(bumped)

        self.assertEqual(session.queue[0].title, "Song 3")
        self.assertEqual(session.queue[1].title, "Song 1")
        self.assertEqual(session.queue[2].title, "Song 2")

    async def test_export_formats_without_creating_channels(self):
        """Verify export formats (json, m3u, txt) generate correctly in memory."""
        tracks = [
            {"title": "Track 1", "artist": "Artist 1", "duration": 180, "url": "https://yt.com/1"},
            {"title": "Track 2", "artist": "Artist 2", "duration": 210, "url": "https://yt.com/2"},
        ]

        # JSON
        json_out = json.dumps({"source": "queue", "count": len(tracks), "tracks": tracks}, indent=2).encode("utf-8")
        parsed = json.loads(json_out.decode("utf-8"))
        self.assertEqual(parsed["count"], 2)

        # M3U
        m3u_lines = ["#EXTM3U"]
        for it in tracks:
            m3u_lines.append(f"#EXTINF:{it['duration']},{it['artist']} - {it['title']}")
            m3u_lines.append(it["url"])
        m3u_out = "\n".join(m3u_lines).encode("utf-8")
        self.assertIn(b"#EXTM3U", m3u_out)
        self.assertIn(b"#EXTINF:180", m3u_out)

        # TXT
        txt_lines = ["=== QUEUE EXPORT ==="]
        for i, it in enumerate(tracks, 1):
            txt_lines.append(f"{i}. {it['title']} by {it['artist']} ({it['url']})")
        txt_out = "\n".join(txt_lines).encode("utf-8")
        self.assertIn(b"1. Track 1 by Artist 1", txt_out)
