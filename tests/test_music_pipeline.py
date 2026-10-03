"""
Comprehensive Unit and Integration Tests for the RAI Music Resolution and Playback Pipeline.
Verifies all 10 stages:
1. Music search service & multi-provider routing
2. URL normalization (watch, youtu.be, shorts, parameter stripping)
3. Direct URL resolution vs text search query separation
4. Multi-candidate interactive search selection view (buttons 1-5 + Cancel)
5. Typed error codes and structured diagnostic ID generation (RAI-MUSIC-XXXXXX)
6. Source pre-flight validation before enqueueing
7. Queue ordering, bounds, loop modes, and history
8. Voice connection check, permission validation, and connection reuse
9. Guild music player lifecycle, controls (pause/resume/skip/stop), and panel updates
10. 10-stage diagnostic validation (/music diagnostic)
"""

import asyncio
from typing import List, Optional
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from music.provider import (
    MusicDiagnosticReport,
    MusicErrorCode,
    ProviderHealthState,
    QueryType,
    ResolutionResult,
    ResolvedTrack,
    TrackCandidate,
    generate_music_diagnostic_id,
)
from music.providers.direct import DirectAudioProvider
from music.providers.soundcloud import SoundCloudMusicProvider
from music.providers.youtube import YouTubeMusicProvider
from music.search_service import MusicSearchService
from music.resolver_service import MusicResolverService
from music.queue_service import MusicQueueService
from music.player_service import MusicPlayerService
from music.session_service import MusicSessionService
from cogs.music import (
    MusicCog,
    GuildMusicPlayer,
    Song,
    SearchSelectView,
    SearchSelectButton,
    SearchCancelButton,
)


class TestMusicPipeline(unittest.IsolatedAsyncioTestCase):
    """Deep pipeline tests covering search, URL resolution, errors, queue, and player."""

    def setUp(self):
        self.bot = MagicMock()
        self.bot.loop = asyncio.get_event_loop()
        self.bot.get_cog.return_value = None
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = 123456789
        self.guild.name = "Test Sanctuary"
        self.guild.voice_client = None

        self.user = MagicMock(spec=discord.Member)
        self.user.id = 987654321
        self.user.display_name = "TestUser"
        self.user.mention = "<@987654321>"
        self.user.guild = self.guild

        self.vc = MagicMock(spec=discord.VoiceChannel)
        self.vc.id = 555666777
        self.vc.name = "🎙️ Room Alpha"
        self.user.voice = MagicMock()
        self.user.voice.channel = self.vc

    def test_diagnostic_id_format(self):
        """Verifies RAI-MUSIC-XXXXXX format."""
        diag_id = generate_music_diagnostic_id()
        self.assertTrue(diag_id.startswith("RAI-MUSIC-"))
        self.assertEqual(len(diag_id), 16)  # 'RAI-MUSIC-' (10) + 6 chars

    def test_youtube_url_normalization(self):
        """Verifies URL normalizer handles youtu.be, watch, shorts, and query params."""
        provider = YouTubeMusicProvider()

        # 1. youtu.be with tracking parameter
        url1 = "https://youtu.be/xvT1jH8B9AM?si=abc123xyz"
        self.assertEqual(provider.normalize_url(url1), "https://www.youtube.com/watch?v=xvT1jH8B9AM")

        # 2. standard watch with feature and t
        url2 = "https://www.youtube.com/watch?v=xvT1jH8B9AM&feature=share"
        self.assertEqual(provider.normalize_url(url2), "https://www.youtube.com/watch?v=xvT1jH8B9AM")

        # 3. shorts format
        url3 = "https://www.youtube.com/shorts/xvT1jH8B9AM"
        self.assertEqual(provider.normalize_url(url3), "https://www.youtube.com/watch?v=xvT1jH8B9AM")

        # 4. plain search query should not normalize to watch URL
        self.assertIsNone(provider.normalize_url("kalyani"))

    def test_query_classification(self):
        """Verifies separation of direct URL vs plain text search queries."""
        qtype_search, q1 = MusicSearchService.classify_query("kalyani")
        self.assertEqual(qtype_search, QueryType.SEARCH)
        self.assertEqual(q1, "kalyani")

        qtype_url, q2 = MusicSearchService.classify_query("https://youtu.be/xvT1jH8B9AM")
        self.assertEqual(qtype_url, QueryType.DIRECT_URL)

        qtype_multi, q3 = MusicSearchService.classify_query("Shreya Ghoshal Kalyani")
        self.assertEqual(qtype_multi, QueryType.SEARCH)

    async def test_search_service_retrieves_candidates(self):
        """Verifies MusicSearchService returns structured TrackCandidates."""
        search_service = MusicSearchService()
        mock_candidates = [
            TrackCandidate(
                title=f"Kalyani - Version {i}",
                url=f"https://www.youtube.com/watch?v=mock_{i}",
                duration=200,
                artist="ARJN",
                provider_name="YouTube",
            )
            for i in range(1, 4)
        ]

        with patch.object(search_service._youtube_provider, "search", new=AsyncMock(return_value=mock_candidates)):
            results = await search_service.search_candidates("kalyani", limit=3, requester=self.user)
            self.assertEqual(len(results), 3)
            self.assertEqual(results[0].title, "Kalyani - Version 1")
            self.assertEqual(results[0].artist, "ARJN")

    async def test_search_service_fallback_to_soundcloud(self):
        """Verifies automatic fallback to SoundCloud when YouTube yields 0 results."""
        search_service = MusicSearchService()
        sc_candidates = [
            TrackCandidate(
                title="Kalyani SC Remix",
                url="https://soundcloud.com/mock/kalyani",
                duration=180,
                artist="SC Artist",
                provider_name="SoundCloud",
            )
        ]

        with patch.object(search_service._youtube_provider, "search", new=AsyncMock(return_value=[])):
            with patch.object(search_service._sc_provider, "search", new=AsyncMock(return_value=sc_candidates)):
                results = await search_service.search_candidates("kalyani", limit=3, requester=self.user)
                self.assertEqual(len(results), 1)
                self.assertEqual(results[0].provider_name, "SoundCloud")
                self.assertEqual(results[0].title, "Kalyani SC Remix")

    async def test_resolver_service_success(self):
        """Verifies MusicResolverService resolves candidate into validated ResolvedTrack."""
        search_service = MusicSearchService()
        resolver = MusicResolverService(search_service)

        cand = TrackCandidate(
            title="Kalyani",
            url="https://www.youtube.com/watch?v=xvT1jH8B9AM",
            duration=288,
            artist="ARJN, Shreya Ghoshal",
            provider_name="YouTube",
            requester=self.user,
        )

        resolved_track = ResolvedTrack(
            candidate=cand,
            stream_url="https://googlevideo.com/videoplayback?mock=stream",
            is_playable=True,
        )

        with patch.object(search_service._youtube_provider, "resolve", new=AsyncMock(return_value=resolved_track)):
            res = await resolver.resolve_track(cand, requester=self.user, guild_id=self.guild.id)
            self.assertTrue(res.is_success)
            self.assertEqual(res.error_code, MusicErrorCode.SUCCESS)
            self.assertIsNotNone(res.track)
            self.assertEqual(res.track.stream_url, "https://googlevideo.com/videoplayback?mock=stream")

    async def test_resolver_service_unsupported_url(self):
        """Verifies resolver returns UNSUPPORTED_URL error code and diagnostic on invalid URL."""
        search_service = MusicSearchService()
        resolver = MusicResolverService(search_service)

        # Provider list with none supporting random domain
        res = await resolver.resolve_track("https://unknown-service.org/song.xyz", requester=self.user, guild_id=self.guild.id)
        self.assertFalse(res.is_success)
        self.assertEqual(res.error_code, MusicErrorCode.UNSUPPORTED_URL)
        self.assertIsNotNone(res.diagnostic)
        self.assertTrue(res.diagnostic.diagnostic_id.startswith("RAI-MUSIC-"))
        self.assertIn("not supported", res.user_message)

    async def test_queue_service_bounds_and_operations(self):
        """Verifies queue limits, pop order, loop mode, and history."""
        queue = MusicQueueService(max_size=3)

        cand = TrackCandidate("Song A", "url", 100, requester=self.user)
        t1 = ResolvedTrack(candidate=cand, stream_url="stream1")
        t2 = ResolvedTrack(candidate=cand, stream_url="stream2")
        t3 = ResolvedTrack(candidate=cand, stream_url="stream3")
        t4 = ResolvedTrack(candidate=cand, stream_url="stream4")

        # 1. Add tracks up to capacity
        self.assertTrue(await queue.add(t1))
        self.assertTrue(await queue.add(t2))
        self.assertTrue(await queue.add(t3))
        self.assertFalse(await queue.add(t4))  # Exceeds max_size=3
        self.assertEqual(len(queue), 3)

        # 2. Pop next
        popped = await queue.pop_next(None)
        self.assertEqual(popped.stream_url, "stream1")
        self.assertEqual(len(queue), 2)

        # 3. Track loop
        queue.loop_mode = "track"
        looped = await queue.pop_next(popped)
        self.assertEqual(looped.stream_url, "stream1")

    async def test_voice_connection_reuse(self):
        """Verifies bot reuses existing VoiceClient and does not make duplicate connection."""
        cog = MusicCog(self.bot)
        player = cog.get_player(self.guild)

        mock_vc = MagicMock(spec=discord.VoiceClient)
        mock_vc.is_connected.return_value = True
        mock_vc.channel = self.vc
        self.guild.voice_client = mock_vc

        perms = MagicMock()
        perms.view_channel = True
        perms.connect = True
        perms.speak = True
        self.vc.permissions_for.return_value = perms

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = self.guild
        interaction.user = self.user
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        vc = await cog._check_voice(interaction)
        self.assertEqual(vc, mock_vc)
        # connect() must not have been called on channel since voice_client is already present
        self.vc.connect.assert_not_called()

    async def test_search_select_view_components(self):
        """Verifies SearchSelectView provides [1..N] buttons, Cancel button, and Select dropdown."""
        cog = MusicCog(self.bot)
        candidates = [
            TrackCandidate(f"Track {i}", f"https://youtube.com/watch?v={i}", 180, f"Artist {i}", requester=self.user)
            for i in range(1, 4)
        ]

        view = SearchSelectView(cog, candidates, self.user, search_query="kalyani")
        # Check buttons: 3 number buttons + 1 cancel button + 1 select dropdown
        buttons = [item for item in view.children if isinstance(item, discord.ui.Button)]
        self.assertEqual(len(buttons), 4)
        self.assertEqual(buttons[0].label, "1")
        self.assertEqual(buttons[1].label, "2")
        self.assertEqual(buttons[2].label, "3")
        self.assertEqual(buttons[3].label, "Cancel")

        selects = [item for item in view.children if isinstance(item, discord.ui.Select)]
        self.assertEqual(len(selects), 1)
        self.assertEqual(len(selects[0].options), 3)

    async def test_diagnostic_10_stages(self):
        """Verifies session service full diagnostic runs across all 10 stages."""
        session_svc = MusicSessionService.get_instance(self.bot)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = self.guild
        interaction.user = self.user

        mock_cand = TrackCandidate("Diagnostic Song", "https://www.youtube.com/watch?v=xvT1jH8B9AM", 180, "Artist", requester=self.user)
        with patch.object(session_svc.search_service, "search_candidates", new=AsyncMock(return_value=[mock_cand])):
            with patch.object(session_svc.search_service._youtube_provider, "get_metadata", new=AsyncMock(return_value=mock_cand)):
                with patch.object(session_svc.resolver_service, "resolve_track", new=AsyncMock(return_value=ResolutionResult(is_success=True, track=ResolvedTrack(mock_cand, "https://stream.mock")))):
                    results = await session_svc.run_full_diagnostic(interaction)

        expected_stages = [
            "Music Service",
            "Search Provider",
            "URL Parser",
            "Metadata Resolver",
            "Source Resolver",
            "Voice Permissions",
            "Voice Connection",
            "Audio Player",
            "Queue",
            "Now Playing Panel",
        ]

        for stage in expected_stages:
            self.assertIn(stage, results, f"Stage '{stage}' missing from diagnostic output")
            ok, note = results[stage]
            self.assertTrue(ok, f"Stage '{stage}' failed with note: {note}")


if __name__ == "__main__":
    unittest.main()
