"""
Unit and Integration Tests for AI Anime Maid Voice DJ, Friend Blend, Cross-Platform Playlist Importer,
and Real-time Web Canvas Visualizer.
"""

import asyncio
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import discord
from discord.ext import commands

from music_bot.database.models import QueuedTrack
from music_bot.services.session_service import GuildMusicSession, PlaybackState
from music_bot.services.maid_dj_service import MaidDJService
from music_bot.services.importer_service import PlaylistImporterService, PlaylistImportResult
from music_bot.services.blend_service import FriendBlendService, FriendBlendResult


def make_test_track(title: str = "A Cruel Angel's Thesis", artist: str = "Yoko Takahashi", requester: str = "Shinji") -> QueuedTrack:
    return QueuedTrack(
        title=title,
        artist=artist,
        url="https://youtube.com/watch?v=mockeva",
        stream_url="https://mock.stream/audio.mp3",
        duration=243,
        thumbnail="https://mock.thumb/eva.jpg",
        requester_id=1457382179981099090,
        requester_name=requester,
    )


class TestMaidDJAndBlendSuite:
    """Test suite verifying Maid Voice DJ, Friend Blend, Importer, and Web Visualizer."""

    # -------------------------------------------------------------------------
    # 1. AI Anime Maid Voice DJ Service Tests
    # -------------------------------------------------------------------------

    def test_01_maid_dj_personalities_templates_and_sanitization(self):
        """1. Verify all 5 Maid DJ personalities generate dialogue correctly."""
        personalities = ["maid", "tsundere", "hype", "chill", "cyberpunk"]
        track = make_test_track("Sparkle (Your Name OST) [Official MV] 4K", "RADWIMPS", "Kishore")

        for p in personalities:
            text = MaidDJService.generate_intro_text(p, track, "Kishore")
            assert len(text) > 10
            # Ensure text is cleaned of video clutter like [Official MV] 4K
            assert "[Official MV]" not in text
            assert "Kishore" in text or "Master" in text

        # Default fallback
        fallback = MaidDJService.generate_intro_text("unknown_mood", track)
        assert len(fallback) > 10

    @pytest.mark.asyncio
    async def test_02_maid_dj_tts_caching_and_audio_bumper(self):
        """2. Verify TTS audio bumper download or cache hit."""
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.status = 200
            # Mock 2000 bytes of mp3 audio
            mock_resp.read.return_value = b"\xff\xfb\x90\x44" * 500
            mock_urlopen.return_value.__enter__.return_value = mock_resp

            path = await MaidDJService.fetch_speech_audio("Goshujin-sama now playing Sparkle nya", lang="en")
            assert path is not None
            assert Path(path).exists()
            assert Path(path).suffix == ".mp3"

    def test_03_maid_dj_dialogue_embed_builder(self):
        """3. Verify dialogue embed formatting and anime badges."""
        track = make_test_track("Idol", "YOASOBI", "Aqua")
        embed = MaidDJService.build_announcement_embed(track, "B-Baka! It's not like I wanted to play Idol for Aqua!", "tsundere")

        assert "TSUNDERE MAID" in embed.title
        assert "B-Baka!" in embed.description
        assert embed.color.value == 0xFF4757  # Tsundere red/pink

    @pytest.mark.asyncio
    async def test_04_maid_dj_in_session_announcement_hook(self):
        """4. Verify MaidDJService announces track when enabled on session."""
        session = GuildMusicSession(guild_id=12345)
        session.maid_voice_dj_enabled = True
        session.maid_dj_personality = "maid"

        mock_channel = AsyncMock()
        session.text_channel = mock_channel

        mock_vc = MagicMock()
        mock_vc.is_connected.return_value = True
        mock_vc.is_playing.return_value = False
        session.voice_client = mock_vc

        track = make_test_track()

        with patch.object(MaidDJService, "fetch_speech_audio", new_callable=AsyncMock) as mock_fetch:
            # Return non-existent file to test graceful fallback
            mock_fetch.return_value = None

            res = await MaidDJService.announce_track(MagicMock(), session, track)
            assert res is True
            mock_channel.send.assert_called_once()
            sent_embed = mock_channel.send.call_args.kwargs.get("embed")
            assert "DEVOTED MAID" in sent_embed.title

    # -------------------------------------------------------------------------
    # 2. Cross-Platform Playlist Importer Tests
    # -------------------------------------------------------------------------

    def test_05_importer_platform_detection(self):
        """5. Verify platform detection for Spotify, YouTube, Apple Music, and SoundCloud."""
        assert PlaylistImporterService.detect_platform("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M") == "Spotify"
        assert PlaylistImporterService.detect_platform("https://www.youtube.com/playlist?list=PLw-VjHDlEOgv_be") == "YouTube"
        assert PlaylistImporterService.detect_platform("https://music.apple.com/us/playlist/anime-hits/pl.u-11zBJrV") == "Apple Music"
        assert PlaylistImporterService.detect_platform("https://soundcloud.com/discover/sets/weekly") == "SoundCloud"
        assert PlaylistImporterService.detect_platform("https://example.com/stream.m3u8") == "Web Stream"

    @pytest.mark.asyncio
    async def test_06_importer_spotify_and_database_persistence(self):
        """6. Verify Spotify playlist import and SQLite insertion."""
        mock_spotify_data = {
            "title": "Anime Neon Anthems",
            "tracks": [
                {"name": "Gurenge", "artist": "LiSA", "url": "https://open.spotify.com/track/1", "duration": 236},
                {"name": "Silhouette", "artist": "KANA-BOON", "url": "https://open.spotify.com/track/2", "duration": 240},
            ],
            "thumbnail": "https://mock.thumb/art.jpg",
        }

        mock_db = MagicMock()
        mock_db.delete_playlist = AsyncMock(return_value=True)
        mock_db.create_playlist = AsyncMock(return_value=42)
        mock_db.add_playlist_track = AsyncMock(return_value=True)

        mock_bot = MagicMock()
        mock_bot.db = mock_db

        with patch("music_bot.services.resolver_service.AudioResolver.resolve_spotify_collection", new_callable=AsyncMock) as mock_res:
            mock_res.return_value = mock_spotify_data

            result = await PlaylistImporterService.import_playlist(
                bot=mock_bot,
                url="https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M",
                guild_id=999,
                user_id=111,
                user_name="Tester",
                custom_name="My Anime Favs",
            )

            assert result.success is True
            assert result.playlist_name == "My Anime Favs"
            assert result.platform == "Spotify"
            assert result.track_count == 2
            mock_db.create_playlist.assert_called_with(999, 111, "My Anime Favs")
            assert mock_db.add_playlist_track.call_count == 2

    # -------------------------------------------------------------------------
    # 3. Friend Blend Service Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_07_friend_blend_generation_and_scoring(self):
        """7. Verify dual-user blend calculations, compatibility scoring, and interweaving."""
        user1 = MagicMock(id=101, display_name="Kishore")
        user2 = MagicMock(id=202, display_name="Alice")

        fav1 = [
            MagicMock(title="Sparkle", artist="RADWIMPS", url="https://yt.com/1", duration=210, thumbnail=None),
            MagicMock(title="Idol", artist="YOASOBI", url="https://yt.com/2", duration=215, thumbnail=None),
            MagicMock(title="Gurenge", artist="LiSA", url="https://yt.com/3", duration=240, thumbnail=None),
        ]
        fav2 = [
            MagicMock(title="Suzume", artist="RADWIMPS", url="https://yt.com/4", duration=230, thumbnail=None),
            MagicMock(title="Monster", artist="YOASOBI", url="https://yt.com/5", duration=205, thumbnail=None),
            MagicMock(title="Homura", artist="LiSA", url="https://yt.com/6", duration=250, thumbnail=None),
        ]

        mock_db = MagicMock()
        mock_db.get_favorites = AsyncMock(side_effect=[fav1, fav2])
        mock_db.get_history = AsyncMock(return_value=[])

        mock_bot = MagicMock()
        mock_bot.db = mock_db

        blend = await FriendBlendService.generate_blend(
            bot=mock_bot,
            guild_id=777,
            user1=user1,
            user2=user2,
            target_size=6,
        )

        assert blend.compatibility_pct >= 70
        assert any(a.lower() in ("radwimps", "yoasobi", "lisa") for a in blend.shared_artists)
        assert len(blend.tracks) == 6
        # Verify tracks alternate between both users' contributions
        assert blend.user1_track_count == 3
        assert blend.user2_track_count == 3

        embed = FriendBlendService.build_blend_embed(blend)
        assert f"{blend.compatibility_pct}% MATCH" in embed.title
        assert any("Top Shared Artists" in f.name for f in embed.fields)

    # -------------------------------------------------------------------------
    # 4. Web Canvas Visualizer Integration Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_08_web_visualizer_routes_render_html(self):
        """8. Verify /canvas and /visualizer routes return the HTML5 audio visualizer interface."""
        from web.server import RaiCommunityOSServer
        from aiohttp import web
        from aiohttp.test_utils import TestClient, TestServer

        mock_db = MagicMock()
        mock_db.is_connected = True
        mock_db.connect = AsyncMock()
        mock_db.close = AsyncMock()
        mock_db.fetch_pending_sync_events = AsyncMock(return_value=[])

        mock_bot = MagicMock()
        mock_bot.db = mock_db
        mock_bot.latency = 0.015

        server = RaiCommunityOSServer(bot=mock_bot, db=mock_db, port=8198)
        app = web.Application()
        server.setup_routes(app)

        test_server = TestServer(app)
        client = TestClient(test_server)
        await client.start_server()

        try:
            # /canvas
            resp_canvas = await client.get("/canvas")
            assert resp_canvas.status == 200
            html_canvas = await resp_canvas.text()
            assert "<!DOCTYPE html>" in html_canvas
            assert "visualizerCanvas" in html_canvas or "MusicMaid" in html_canvas

            # /visualizer
            resp_viz = await client.get("/visualizer")
            assert resp_viz.status == 200
            html_viz = await resp_viz.text()
            assert "<!DOCTYPE html>" in html_viz
        finally:
            await client.close()
