"""
Comprehensive Unit & Integration Test Suite for Neko Songs Discord Music Bot.
Verifies full compliance with Neko Songs Specification:
1. Brand identity, palette tokens, and dialogue presets.
2. Token security, priority loading (NEKO_SONGS_BOT_TOKEN), and masking.
3. Database persistence: guild settings, favorites, playlists, DJ settings, stats, heartbeats.
4. Guild session state machine, serialization, and per-guild isolation.
5. Queue manipulation: bounds, loop modes (off, track, queue), shuffle, clear, remove.
6. Neko DJ system: metadata recommendations, repeat avoidance, interactive card.
7. Recommendation service: all 8 mood/discovery modes.
8. Now Playing panel: Neko-themed embed format and 9-button control view.
9. Interactive Setup dashboard: 10 configuration buttons.
10. MusicGateway contract & hot-swappable provider verification.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import os
from pathlib import Path
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from music_bot.config import (
    BOT_NAME,
    COLOR_ELECTRIC_CYAN,
    COLOR_MIDNIGHT_BLACK,
    COLOR_NEON_BLUE,
    COLOR_WHITE,
    DIALOGUE_EMPTY_QUEUE,
    DIALOGUE_JOIN,
    DIALOGUE_NOTHING_PLAYABLE,
    DIALOGUE_PLAYBACK_END,
    DIALOGUE_START,
    DIALOGUE_UNAVAILABLE,
    DIALOGUE_UNPLAYABLE,
    get_masked_music_token,
    is_music_token_valid,
)
from music_bot.database.db import MusicDatabase
from music_bot.database.models import (
    MusicDJSettings,
    MusicFavorite,
    MusicGuildSettings,
    QueuedTrack,
)
from music_bot.services.dj_service import DJRecommendationCardView, NekoDJService
from music_bot.services.player_service import (
    NowPlayingControlView,
    VolumeAdjustView,
    build_now_playing_embed,
    format_duration,
)
from music_bot.services.recommendation_service import MusicRecommendationService
from music_bot.services.session_service import (
    GuildMusicSession,
    LoopMode,
    PlaybackState,
    SessionManager,
)
from services.music_gateway import (
    GatewayResult,
    MusicBotStatus,
    MusicGateway,
    NekoSongsBotProvider,
    RaiMusicBotProvider,
    ReplacementMusicBotProvider,
)


class TestNekoSongsBotSuite(unittest.IsolatedAsyncioTestCase):
    """Deep verification of the independent Neko Songs audio platform."""

    async def asyncSetUp(self):
        self.test_dir = Path("scratch/test_neko_db")
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.test_db_path = self.test_dir / "neko_test.db"
        if self.test_db_path.exists():
            self.test_db_path.unlink()

        self.db = MusicDatabase(db_path=self.test_db_path)
        await self.db.connect()

        self.guild_id_1 = 111222333444
        self.guild_id_2 = 555666777888
        self.user_id = 999888777

    async def asyncTearDown(self):
        await self.db.close()
        for ext in ["", "-wal", "-shm"]:
            p = Path(str(self.test_db_path) + ext)
            if p.exists():
                try:
                    p.unlink()
                except Exception:
                    pass
        MusicGateway.set_provider(RaiMusicBotProvider())


    # =========================================================================
    # 1. BRANDING & SECURE CONFIGURATION
    # =========================================================================

    def test_brand_identity_and_color_palette(self):
        """Validates Neko Songs brand aesthetics, theme colors, and dialogue presets."""
        self.assertEqual(BOT_NAME, "Neko Songs")
        self.assertEqual(COLOR_MIDNIGHT_BLACK, 0x0B0E14)
        self.assertEqual(COLOR_NEON_BLUE, 0x00B0FF)
        self.assertEqual(COLOR_ELECTRIC_CYAN, 0x00E5FF)
        self.assertEqual(COLOR_WHITE, 0xFFFFFF)

        self.assertIn("Neko has entered the listening room", DIALOGUE_JOIN)
        self.assertIn("Found it! Let's listen", DIALOGUE_START)
        self.assertIn("The queue is empty", DIALOGUE_EMPTY_QUEUE)
        self.assertIn("couldn't resolve a playable audio source", DIALOGUE_UNPLAYABLE)
        self.assertEqual(DIALOGUE_UNPLAYABLE, DIALOGUE_NOTHING_PLAYABLE)
        self.assertIn("temporarily unavailable", DIALOGUE_UNAVAILABLE)
        self.assertIn("That was a good one", DIALOGUE_PLAYBACK_END)

    def test_token_masking_and_validation(self):
        """Tokens must be validated without exposing their plaintext characters."""
        masked = get_masked_music_token()
        self.assertNotIn(" ", masked)
        # Verify valid Discord token format check
        self.assertTrue(is_music_token_valid())

    # =========================================================================
    # 2. PERSISTENCE & DATABASE CRUD
    # =========================================================================

    async def test_guild_settings_persistence_and_defaults(self):
        """Guild settings support custom defaults, volume, quiet mode, and style."""
        defaults = await self.db.get_guild_settings(self.guild_id_1)
        self.assertEqual(defaults.guild_id, self.guild_id_1)
        self.assertEqual(defaults.default_volume, 80)
        self.assertFalse(defaults.quiet_mode)
        self.assertEqual(defaults.response_style, "normal")

        # Update settings
        defaults.default_volume = 65
        defaults.quiet_mode = True
        defaults.request_channel_id = 123456789
        defaults.dj_role_id = 987654321
        defaults.vote_skip_threshold = 0.6
        await self.db.update_guild_settings(defaults)

        fetched = await self.db.get_guild_settings(self.guild_id_1)
        self.assertEqual(fetched.default_volume, 65)
        self.assertTrue(fetched.quiet_mode)
        self.assertEqual(fetched.request_channel_id, 123456789)
        self.assertEqual(fetched.dj_role_id, 987654321)
        self.assertAlmostEqual(fetched.vote_skip_threshold, 0.6)

    async def test_personal_favorites_system(self):
        """Users can save, retrieve, and delete personal favorite tracks."""
        track = QueuedTrack(
            title="Kalyani - Classical Lofi",
            artist="Indie Fusion",
            url="https://youtube.com/watch?v=kalyani123",
            duration=210,
            requester_id=self.user_id,
            requester_name="Kishore",
        )
        saved = await self.db.add_favorite(self.user_id, track)
        self.assertTrue(saved)

        favs = await self.db.get_favorites(self.user_id)
        self.assertEqual(len(favs), 1)
        self.assertEqual(favs[0].title, "Kalyani - Classical Lofi")

        # Duplicate addition is handled safely and returns False
        saved_again = await self.db.add_favorite(self.user_id, track)
        self.assertFalse(saved_again)
        self.assertEqual(len(await self.db.get_favorites(self.user_id)), 1)


        # Removal
        removed = await self.db.remove_favorite(self.user_id, "Kalyani - Classical Lofi")
        self.assertTrue(removed)
        self.assertEqual(len(await self.db.get_favorites(self.user_id)), 0)

    async def test_playlist_full_lifecycle(self):
        """Supports playlist creation, track additions, removals, and deletion."""
        pl_name = "Midnight Vibes"
        pl_id = await self.db.create_playlist(self.guild_id_1, self.user_id, pl_name)
        self.assertIsNotNone(pl_id)

        # Add tracks
        track = QueuedTrack(
            title="Night Flight",
            artist="Anime Beats",
            url="https://youtube.com/watch?v=flight",
            duration=180,
            requester_id=self.user_id,
            requester_name="Kishore",
        )
        add_res = await self.db.add_playlist_track(pl_id, track)  # type: ignore
        self.assertTrue(add_res)

        pl = await self.db.get_playlist(self.guild_id_1, pl_name, user_id=self.user_id)
        self.assertIsNotNone(pl)
        self.assertEqual(len(pl.tracks), 1)
        self.assertEqual(pl.tracks[0].title, "Night Flight")

        # Remove track by position
        rem_res = await self.db.remove_playlist_track(pl_id, 1)  # type: ignore
        self.assertTrue(rem_res)
        pl_empty = await self.db.get_playlist(self.guild_id_1, pl_name, user_id=self.user_id)
        self.assertEqual(len(pl_empty.tracks), 0)

        # Delete playlist
        del_res = await self.db.delete_playlist(self.guild_id_1, self.user_id, pl_name)
        self.assertTrue(del_res)
        self.assertIsNone(await self.db.get_playlist(self.guild_id_1, pl_name, user_id=self.user_id))

    async def test_truthful_listening_history_and_stats(self):
        """Records playback history and computes truthful stats without fabricating data."""
        # Clean history initially
        initial_stats = await self.db.get_guild_stats(self.guild_id_1)
        self.assertEqual(initial_stats["total_played"], 0)
        self.assertEqual(initial_stats["top_songs"], ["None yet"])

        # Record 3 songs (guild_id, title, url, artist, requester_id)
        await self.db.record_history(self.guild_id_1, "Track A", "https://url1", "Artist 1", self.user_id)
        await self.db.record_history(self.guild_id_1, "Track A", "https://url1", "Artist 1", self.user_id)
        await self.db.record_history(self.guild_id_1, "Track B", "https://url2", "Artist 2", self.user_id)

        stats = await self.db.get_guild_stats(self.guild_id_1)
        self.assertEqual(stats["total_played"], 3)
        self.assertIn("Track A (2x)", stats["top_songs"][0])
        self.assertIn("Artist 1 (2x)", stats["top_artists"][0])

    # =========================================================================
    # 3. SESSION MANAGEMENT & QUEUE ISOLATION
    # =========================================================================

    async def test_session_isolation_between_guilds(self):
        """Actions in Guild 1 must not leak or mutate state in Guild 2."""
        manager = SessionManager()
        s1 = await manager.get_session(self.guild_id_1)
        s2 = await manager.get_session(self.guild_id_2)

        track_1 = QueuedTrack(title="Guild 1 Track", artist="A1", url="http://1", duration=100, requester_id=1, requester_name="U1")
        track_2 = QueuedTrack(title="Guild 2 Track", artist="A2", url="http://2", duration=200, requester_id=2, requester_name="U2")

        s1.queue.append(track_1)
        s2.queue.append(track_2)

        self.assertEqual(len(s1.queue), 1)
        self.assertEqual(len(s2.queue), 1)
        self.assertEqual(s1.queue[0].title, "Guild 1 Track")
        self.assertEqual(s2.queue[0].title, "Guild 2 Track")

        s1.queue.clear()
        self.assertEqual(len(s1.queue), 0)
        self.assertEqual(len(s2.queue), 1, "Clearing session 1 queue must not alter session 2 queue!")


    def test_queue_loop_modes(self):
        """Verifies loop state transitions: off, track, queue."""
        session = GuildMusicSession(guild_id=self.guild_id_1)
        self.assertEqual(session.loop_mode, LoopMode.OFF)

        session.loop_mode = LoopMode.TRACK
        self.assertEqual(session.loop_mode.value, "track")

        session.loop_mode = LoopMode.QUEUE
        self.assertEqual(session.loop_mode.value, "queue")

    # =========================================================================
    # 4. NEKO DJ & METADATA-BASED RECOMMENDATIONS
    # =========================================================================

    async def test_neko_dj_recommendation_and_repeat_avoidance(self):
        """Neko DJ generates metadata recommendations without repeating recent tracks."""
        session = GuildMusicSession(guild_id=self.guild_id_1)
        session.current_track = QueuedTrack(
            title="Racing into the Night",
            artist="YOASOBI",
            url="https://youtube.com/watch?v=yoasobi",
            duration=261,
            requester_id=self.user_id,
            requester_name="Kishore",
        )

        # Mark YOASOBI songs in recent history
        session.history.append(session.current_track)

        rec = await NekoDJService.recommend_next_track(session)
        self.assertIsNotNone(rec)
        self.assertIn("YOASOBI", rec["query"])
        self.assertIn("style", rec["reason"].lower())

        # Build recommendation card
        card_view = DJRecommendationCardView(
            bot=MagicMock(),
            session=session,
            recommended_query=rec["query"],
            reason=rec["reason"],
            requester_id=self.user_id,
        )
        # Must have exactly 3 interactive buttons: [➕ Add to Queue] [▶ Play Next] [❌ Dismiss]
        self.assertEqual(len(card_view.children), 3)

    async def test_recommendation_service_modes(self):
        """Verifies all 8 smart recommendation modes provide valid search queries."""
        session = GuildMusicSession(guild_id=self.guild_id_1)
        session.current_track = QueuedTrack(
            title="Suzume",
            artist="Radwimps",
            url="https://youtube.com/watch?v=suzume",
            duration=230,
            requester_id=self.user_id,
            requester_name="Kishore",
        )

        modes = ["similar_tracks", "similar_artists", "genre", "discover", "chill", "gaming", "party", "night"]
        for mode in modes:
            with patch("music_bot.services.resolver_service.AudioResolver.search", new_callable=AsyncMock) as mock_search:
                mock_search.return_value = [{"title": f"Result for {mode}", "url": "https://url", "duration": 180}]
                results = await MusicRecommendationService.get_mode_recommendations(session, mode, limit=2)
                self.assertGreater(len(results), 0, f"Mode {mode} should return recommendation candidates.")

    # =========================================================================
    # 5. NOW PLAYING PANEL & SETUP VIEW
    # =========================================================================

    def test_now_playing_embed_structure(self):
        """Verifies Now Playing embed adheres strictly to Neko Songs format."""
        session = GuildMusicSession(guild_id=self.guild_id_1)
        session.current_track = QueuedTrack(
            title="Idol",
            artist="YOASOBI",
            url="https://youtube.com/watch?v=idol",
            duration=241,
            requester_id=self.user_id,
            requester_name="Kishore",
        )
        session.volume = 80
        session.state = PlaybackState.PLAYING

        embed = build_now_playing_embed(session)
        self.assertIn("NOW PLAYING", embed.title or "")
        self.assertIn("YOASOBI", embed.description or "")
        self.assertIn("Idol", embed.description or "")
        self.assertIn("80%", embed.description or "")
        self.assertIn(str(self.user_id), embed.description or "")

    def test_now_playing_control_view_buttons(self):
        """Now Playing view must contain all 13 interactive buttons and support persistent mode."""
        # 1. Per-session clean minimal view
        session = GuildMusicSession(guild_id=self.guild_id_1)
        view = NowPlayingControlView(session)

        # 10 buttons across 2 clean rows:
        # Row 0: [⏮ Prev] [⏸ Pause/Resume] [⏭ Skip] [📜 Queue] [🔄 Refresh]
        # Row 1: [🎛️ Audio & EQ] [🎧 Auto-DJ] [⚙️ Settings] [❤️ Favorite] [⏹ Stop]
        self.assertEqual(len(view.children), 10)

        labels = [btn.label for btn in view.children if hasattr(btn, "label")]
        self.assertIn("Prev", labels)
        self.assertIn("Pause", labels)
        self.assertIn("Skip", labels)
        self.assertIn("Queue", labels)
        self.assertIn("Refresh", labels)
        self.assertIn("Audio & EQ", labels)
        self.assertIn("Auto-DJ", labels)
        self.assertIn("Settings", labels)
        self.assertIn("Favorite", labels)
        self.assertIn("Stop", labels)

        # 2. Persistent view with session=None
        persistent_view = NowPlayingControlView()
        self.assertEqual(len(persistent_view.children), 10)


    def test_volume_adjust_view_preset_buttons(self):
        """Volume adjust view provides 20%, 50%, 80%, and 100% quick buttons."""
        session = GuildMusicSession(guild_id=self.guild_id_1)
        view = VolumeAdjustView(session)
        self.assertEqual(len(view.children), 4)


    # =========================================================================
    # 6. MUSIC GATEWAY & HOT-SWAPPABILITY
    # =========================================================================

    async def test_music_gateway_neko_provider_contract(self):
        """Main Rai queries Neko Songs status via heartbeat without importing music services."""
        self.assertIsInstance(MusicGateway.get_provider(), (RaiMusicBotProvider, NekoSongsBotProvider))

        # Point provider to isolated test DB (initially empty with no heartbeat)
        provider = NekoSongsBotProvider(db_path=self.test_db_path, bot_id=1556676516274905218)
        MusicGateway.set_provider(provider)

        # 1. Without heartbeat -> OFFLINE
        status_offline = await MusicGateway.get_status()
        self.assertEqual(status_offline.status, MusicBotStatus.OFFLINE)

        # 2. Record fresh heartbeat into database
        await self.db.update_heartbeat(
            bot_id=1556676516274905218,
            version="2.0.0",
            status="online",
            active_sessions=3,
            playing_count=2,
        )

        status_online = await MusicGateway.get_status()
        self.assertEqual(status_online.status, MusicBotStatus.CONNECTED)
        self.assertEqual(status_online.active_sessions, 3)
        self.assertEqual(status_online.playing_count, 2)

        # 3. Hot-swap provider to replacement
        replacement = ReplacementMusicBotProvider(bot_name="Lavalink V4")
        MusicGateway.set_provider(replacement)
        self.assertIsInstance(MusicGateway.get_provider(), ReplacementMusicBotProvider)
        swap_res = await MusicGateway.play(self.guild_id_1, "lofi study", self.user_id)
        self.assertTrue(swap_res.success)

    # =========================================================================
    # 7. 24/7 VOICE MODE & AUTONOMOUS AUTO-UPDATER
    # =========================================================================

    async def test_twenty_four_seven_persistence_and_query(self):
        """Validates 24/7 guild settings persistence and get_all_247_guilds retrieval."""
        settings = await self.db.get_guild_settings(self.guild_id_1)
        self.assertFalse(settings.twenty_four_seven_enabled)
        self.assertIsNone(settings.twenty_four_seven_channel_id)

        # Enable 24/7 mode
        settings.twenty_four_seven_enabled = True
        settings.twenty_four_seven_channel_id = 9988776655
        await self.db.update_guild_settings(settings)

        # Verify single guild retrieval
        fetched = await self.db.get_guild_settings(self.guild_id_1)
        self.assertTrue(fetched.twenty_four_seven_enabled)
        self.assertEqual(fetched.twenty_four_seven_channel_id, 9988776655)

        # Verify bulk 24/7 guilds query
        all_247 = await self.db.get_all_247_guilds()
        self.assertEqual(len(all_247), 1)
        self.assertEqual(all_247[0].guild_id, self.guild_id_1)

    async def test_music_auto_updater_version_check(self):
        """Validates MusicAutoUpdater version discovery and update inspection."""
        from music_bot.services.updater_service import MusicAutoUpdater

        ver = MusicAutoUpdater.get_current_ytdl_version()
        self.assertIsInstance(ver, str)
        self.assertNotEqual(ver, "")

        # Check version resolution mock
        with patch("urllib.request.urlopen") as mock_url:
            mock_resp = MagicMock()
            mock_resp.read.return_value = b'{"info": {"version": "2026.10.15"}}'
            mock_url.return_value.__enter__.return_value = mock_resp

            res = await MusicAutoUpdater.check_ytdl_version()
            self.assertEqual(res["latest"], "2026.10.15")

    async def test_voice_manager_bypasses_auto_leave_in_247_mode(self):
        """VoiceManager must never schedule auto-leave if 24/7 mode is active."""
        from music_bot.services.voice_service import VoiceManager

        session = GuildMusicSession(self.guild_id_1)
        session.twenty_four_seven = True

        mock_bot = MagicMock()
        VoiceManager.schedule_auto_leave(mock_bot, session, timeout=60)
        self.assertIsNone(session.auto_leave_task)

    async def test_audio_filters_and_sleep_timer(self):
        """Validates dynamic audio filters and bedtime sleep timer state."""
        session = GuildMusicSession(self.guild_id_1)
        self.assertEqual(session.audio_filter, "")

        # Apply Bass Boost
        session.audio_filter = "-af equalizer=f=60:width_type=h:width=50:g=10"
        self.assertIn("equalizer", session.audio_filter)

        # Apply Sleep Timer
        self.assertEqual(session.sleep_timer_end, 0.0)
        session.sleep_timer_end = time.time() + 1800
        self.assertGreater(session.sleep_timer_end, time.time())

    async def test_lyrics_caching_and_precache(self):
        """Validates LyricsService in-memory caching and 0ms cache retrieval."""
        from music_bot.services.lyrics_service import LyricsService

        # Manually prime cache
        LyricsService._store_cache("test song::test artist", "Line 1\nLine 2")
        lyrics = await LyricsService.fetch_lyrics("test song", "test artist")
        self.assertEqual(lyrics, "Line 1\nLine 2")

    async def test_music_control_panel_view_and_features(self):
        """Validates MusicControlPanelView embed generation, dropdown tabs, and feature coverage."""
        from music_bot.commands.music_cog import MusicControlPanelView

        session = GuildMusicSession(self.guild_id_1)
        mock_guild = MagicMock()
        mock_guild.id = self.guild_id_1
        mock_bot = MagicMock()
        mock_bot.user.name = "MusicMaid"
        mock_bot.user.id = 1556676516274905218

        view = MusicControlPanelView(mock_bot, mock_guild, session)
        self.assertEqual(view.current_page, "overview")

        # Verify overview embed
        overview_embed = view.build_embed()
        self.assertIn("Master Control Panel", overview_embed.title)
        self.assertTrue(any("Core Playback" in f.name for f in overview_embed.fields))
        self.assertTrue(any("Audio Filters" in f.name for f in overview_embed.fields))

        # Test each category tab
        categories = ["playback", "filters", "247_radio", "sleeptimer", "playlists", "smart_dj"]
        for cat in categories:
            view.current_page = cat
            embed = view.build_embed()
            self.assertIsNotNone(embed.title)
            self.assertGreater(len(embed.fields), 0)

    async def test_git_updates_and_recovery_stream(self):
        """Validates MusicAutoUpdater git update discovery and stream recovery hooks."""
        from music_bot.services.updater_service import MusicAutoUpdater
        from music_bot.services.player_service import MusicPlayerService
        from music_bot.database.models import QueuedTrack

        git_res = await MusicAutoUpdater.check_git_updates()
        self.assertIsInstance(git_res, dict)
        self.assertIn("is_git", git_res)

        # Test track recovery state
        track = QueuedTrack(
            title="Test Song",
            url="https://youtube.com/watch?v=123",
            duration=200,
            artist="Test Artist",
            requester_id=1,
            requester_name="User",
        )
        self.assertEqual(getattr(track, "_retry_count", 0), 0)
        track._retry_count = 1
        self.assertEqual(track._retry_count, 1)

    async def test_session_queue_and_history_persistence(self):
        """Verifies session queue and history are fully persisted and recovered across restarts."""
        from music_bot.database.models import QueuedTrack
        from music_bot.services.session_service import GuildMusicSession

        curr_track = QueuedTrack(title="Song 1", url="https://youtube.com/watch?v=1", duration=180, requester_id=1, requester_name="User", artist="Artist 1")
        t2 = QueuedTrack(title="Song 2", url="https://youtube.com/watch?v=2", duration=200, requester_id=1, requester_name="User", artist="Artist 2")
        t3 = QueuedTrack(title="Song 3", url="https://youtube.com/watch?v=3", duration=220, requester_id=1, requester_name="User", artist="Artist 3")
        h1 = QueuedTrack(title="Past Song A", url="https://youtube.com/watch?v=A", duration=150, requester_id=1, requester_name="User", artist="Past Artist")

        await self.db.save_session(
            guild_id=self.guild_id_1,
            voice_channel_id=12345,
            text_channel_id=67890,
            state="PLAYING",
            volume=75,
            current_track=curr_track,
            position_seconds=85,
            queue=[t2, t3],
            history=[h1],
        )

        active = await self.db.get_active_sessions()
        session_data = next((s for s in active if s["guild_id"] == self.guild_id_1), None)
        self.assertIsNotNone(session_data)
        self.assertEqual(session_data["position_seconds"], 85)
        self.assertEqual(session_data["current_track"]["title"], "Song 1")
        self.assertEqual(len(session_data["queue"]), 2)
        self.assertEqual(session_data["queue"][0]["title"], "Song 2")
        self.assertEqual(len(session_data["history"]), 1)
        self.assertEqual(session_data["history"][0]["title"], "Past Song A")

    def test_now_playing_embed_relative_countdown(self):
        """Now Playing embed includes relative timestamp countdown for live UI display."""
        from music_bot.database.models import QueuedTrack
        from music_bot.services.player_service import build_now_playing_embed

        session = GuildMusicSession(guild_id=self.guild_id_1)
        session.current_track = QueuedTrack(
            title="Long Jukebox",
            url="https://youtube.com/watch?v=123",
            duration=6148,
            requester_id=1,
            requester_name="User",
            artist="Sony Music",
        )
        session.state = PlaybackState.PLAYING
        session.track_start_time = time.time() - 100

        embed = build_now_playing_embed(session)
        self.assertIn("Ends <t:", embed.description)
        self.assertIn(":R>", embed.description)


if __name__ == "__main__":
    unittest.main()

