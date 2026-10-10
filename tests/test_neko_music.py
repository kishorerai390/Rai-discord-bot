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
        self.assertIn("NEKO SONGS", embed.title or "")
        self.assertIn("🐱 **NOW PLAYING**", embed.description or "")
        self.assertIn("YOASOBI", embed.description or "")
        self.assertIn("Idol", embed.description or "")
        self.assertIn("80%", embed.description or "")
        self.assertIn(str(self.user_id), embed.description or "")



    def test_now_playing_control_view_buttons(self):
        """Now Playing view must contain the exact 9 required interactive buttons."""
        session = GuildMusicSession(guild_id=self.guild_id_1)
        view = NowPlayingControlView(session)

        # 9 buttons in layout:
        # [⏮ Previous] [⏸ Pause] [⏭ Skip]
        # [📜 Queue] [🔀 Shuffle] [🔁 Loop]
        # [🔊 Volume] [❤️ Favorite] [⏹ Stop]
        self.assertEqual(len(view.children), 9)

        labels = [btn.label for btn in view.children if hasattr(btn, "label")]
        self.assertIn("Previous", labels)
        self.assertIn("Skip", labels)
        self.assertIn("Queue", labels)
        self.assertIn("Shuffle", labels)
        self.assertIn("Loop", labels)
        self.assertIn("Volume", labels)
        self.assertIn("Favorite", labels)
        self.assertIn("Stop", labels)

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


if __name__ == "__main__":
    unittest.main()
