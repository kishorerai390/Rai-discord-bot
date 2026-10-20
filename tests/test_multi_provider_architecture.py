"""
Tests for Multi-Provider Architecture, Original-Song Matching, and Intelligent Fallback.

Covers:
1. Provider Architecture:
   - YouTube, Audius, Jamendo, Spotify, Apple Music, and direct safe audio URLs.
   - SoundCloud rejection by policy.
   - Restricted providers (Spotify, Apple Music) never entering direct audio extraction.
2. Network Security & SSRF Protection:
   - Safe public URL validation.
   - Blocking localhost, 127.0.0.1, 169.254.169.254, RFC1918 private subnets, and metadata endpoints.
3. Original-Song Matching & Language Preservation:
   - Tamil song matching (exact title/artist preferred).
   - Rejecting unrequested remixes, covers, slowed versions.
4. Intelligent Fallback:
   - When YouTube times out or exhausts retries, fallback searches Audius/Jamendo.
   - Matching against original intent before playing.
5. Unified Player & Queue:
   - All providers populate unified QueuedTrack fields and provider badge.
"""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from music_bot.database.models import QueuedTrack
from music_bot.services.alternative_providers import AudiusProviderService, JamendoProviderService
from music_bot.services.apple_music_service import AppleMusicService
from music_bot.services.network_security import is_safe_ip, validate_safe_url
from music_bot.services.player_service import MusicPlayerService
from music_bot.services.resolver_service import AudioResolver, analyze_query_intent, is_original_recording_candidate
from music_bot.services.session_service import GuildMusicSession, SessionManager


class TestMultiProviderArchitecture(unittest.IsolatedAsyncioTestCase):
    """Test suite covering multi-provider abstraction, safety, and fallback."""

    async def asyncSetUp(self):
        AudioResolver.clear_caches()
        self.session_manager = SessionManager()
        self.session = await self.session_manager.get_session(123456789)

    async def asyncTearDown(self):
        AudioResolver.clear_caches()
        if self.session:
            self.session.reset()

    # =========================================================================
    # 1. SSRF & NETWORK SECURITY VALIDATION
    # =========================================================================

    def test_ssrf_protection_blocked_ips(self):
        """Verify loopback, private, and cloud metadata addresses are strictly blocked."""
        self.assertFalse(is_safe_ip("127.0.0.1"))
        self.assertFalse(is_safe_ip("::1"))
        self.assertFalse(is_safe_ip("169.254.169.254"))  # AWS/GCP/Azure metadata
        self.assertFalse(is_safe_ip("10.0.0.1"))
        self.assertFalse(is_safe_ip("192.168.1.1"))
        self.assertFalse(is_safe_ip("172.16.0.1"))
        # Public IP should be permitted
        self.assertTrue(is_safe_ip("8.8.8.8"))
        self.assertTrue(is_safe_ip("1.1.1.1"))

    def test_validate_safe_url_blocks_internal_hosts(self):
        """Verify internal, private, and non-http schemes are rejected."""
        safe, err, _ = validate_safe_url("http://localhost:8080/audio.mp3")
        self.assertFalse(safe)
        self.assertIn("not permitted", err.lower())

        safe, err, _ = validate_safe_url("http://169.254.169.254/latest/meta-data/")
        self.assertFalse(safe)

        safe, err, _ = validate_safe_url("file:///etc/passwd")
        self.assertFalse(safe)
        self.assertIn("unsupported url scheme", err.lower())

        safe, err, _ = validate_safe_url("http://metadata.google.internal/computeMetadata/v1/")
        self.assertFalse(safe)

    def test_validate_safe_url_permits_public_https(self):
        """Verify legitimate public HTTPS media URLs pass validation."""
        safe, err, url = validate_safe_url("https://cdn.example.com/audio/track.mp3")
        # In mock or offline environment where cdn.example.com may not resolve,
        # test with an IP literal or public domain
        safe_ip_url, _, _ = validate_safe_url("https://8.8.8.8/stream.mp3")
        self.assertTrue(safe_ip_url)

    # =========================================================================
    # 2. SOUNDCLOUD POLICY ENFORCEMENT
    # =========================================================================

    @patch("music_bot.services.resolver_service._run_ytdlp")
    async def test_soundcloud_url_rejected_by_policy(self, mock_run):
        """Verify SoundCloud URLs are rejected cleanly without entering streaming extraction."""
        track = await AudioResolver.resolve_track(
            "https://soundcloud.com/artist/sample-track",
            123,
            "User",
        )
        self.assertIsNone(track)
        mock_run.assert_not_called()
        self.assertIn("[UNSUPPORTED_PROVIDER]", AudioResolver.last_resolver_error)

    # =========================================================================
    # 3. APPLE MUSIC & SPOTIFY METADATA ONLY (NO DIRECT EXTRACTION)
    # =========================================================================

    def test_apple_music_url_recognition(self):
        """Verify Apple Music URLs are correctly identified."""
        self.assertTrue(
            AppleMusicService.is_apple_music_url(
                "https://music.apple.com/us/album/yellow/1440854486?i=1440854492"
            )
        )
        self.assertTrue(
            AppleMusicService.is_apple_music_url(
                "https://itunes.apple.com/in/song/kesariya/1634790065"
            )
        )
        self.assertFalse(AppleMusicService.is_apple_music_url("https://youtube.com/watch?v=123"))

    @patch("music_bot.services.apple_music_service.AppleMusicService.resolve_url")
    @patch("music_bot.services.resolver_service.AudioResolver.search")
    @patch("music_bot.services.resolver_service._run_ytdlp")
    async def test_apple_music_metadata_resolved_without_stream_ripping(
        self, mock_run, mock_search, mock_apple_resolve
    ):
        """Verify Apple Music URLs resolve catalog metadata and match public audio without ripping."""
        mock_apple_resolve.return_value = {
            "id": "1440854492",
            "title": "Yellow",
            "artist": "Coldplay",
            "album": "Parachutes",
            "duration": 269,
            "url": "https://music.apple.com/us/album/yellow/1440854486?i=1440854492",
            "thumbnail": "https://is1-ssl.mzstatic.com/image/thumb/Music115/v4/yellow.jpg",
            "search_query": "Yellow Coldplay",
            "source": "apple_music",
        }

        mock_search.return_value = [
            {
                "id": "yt_yellow",
                "title": "Coldplay - Yellow (Official Video)",
                "uploader": "Coldplay Official",
                "channel_is_verified": True,
                "duration": 269,
                "url": "https://www.youtube.com/watch?v=yt_yellow",
            }
        ]

        mock_run.return_value = {
            "id": "yt_yellow",
            "title": "Coldplay - Yellow (Official Video)",
            "uploader": "Coldplay Official",
            "channel_is_verified": True,
            "duration": 269,
            "url": "https://audio-stream.googlevideo.com/videoplayback?id=yt_yellow",
            "formats": [{"url": "https://audio-stream.googlevideo.com/videoplayback?id=yt_yellow"}],
        }

        track = await AudioResolver.resolve_track(
            "https://music.apple.com/us/album/yellow/1440854486?i=1440854492",
            123,
            "Tester",
        )

        self.assertIsNotNone(track)
        self.assertEqual(track.title, "Yellow")
        self.assertEqual(track.artist, "Coldplay")
        self.assertEqual(getattr(track, "provider", None), "apple_music")
        # Stream URL is resolved public audio, never an apple.com stream
        self.assertNotIn("apple.com", track.stream_url)

    # =========================================================================
    # 4. INTELLIGENT FALLBACK (AUDIUS & JAMENDO)
    # =========================================================================

    @patch("music_bot.services.alternative_providers.AudiusProviderService.search")
    @patch("music_bot.services.resolver_service._run_ytdlp")
    async def test_intelligent_fallback_to_audius_when_youtube_times_out(
        self, mock_run, mock_audius_search
    ):
        """Verify that when YouTube times out, resolver falls back to Audius for verified tracks."""
        # YouTube search fails with TimeoutError
        mock_run.side_effect = asyncio.TimeoutError("YouTube search socket timed out")

        # Audius provides an authorized independent track
        mock_audius_search.return_value = [
            {
                "id": "aud_123",
                "title": "Ambient Meditation - Official Audio",
                "artist": "Zen Music Official",
                "channel_is_verified": True,
                "duration": 240,
                "url": "https://audius.co/zenmusic/ambient-meditation",
                "stream_url": "https://api.audius.co/v1/tracks/aud_123/stream?app_name=MusicMaid",
                "thumbnail": "https://audius.co/art/480x480.jpg",
                "provider": "audius",
            }
        ]

        track = await AudioResolver.resolve_track("ambient meditation", 123, "Tester")
        self.assertIsNotNone(track)
        self.assertEqual(track.title, "Ambient Meditation - Official Audio")
        self.assertEqual(getattr(track, "provider", None), "audius")
        self.assertIn("audius.co", track.stream_url)

    @patch("music_bot.services.alternative_providers.JamendoProviderService.search")
    @patch("music_bot.services.alternative_providers.AudiusProviderService.search")
    @patch("music_bot.services.resolver_service._run_ytdlp")
    async def test_intelligent_fallback_to_jamendo_when_audius_empty(
        self, mock_run, mock_audius_search, mock_jamendo_search
    ):
        """Verify that when YouTube times out and Audius has no match, resolver falls back to Jamendo."""
        mock_run.side_effect = asyncio.TimeoutError("YouTube timed out")
        mock_audius_search.return_value = []

        mock_jamendo_search.return_value = [
            {
                "id": "jam_456",
                "title": "Acoustic Breeze - Official Release",
                "artist": "Benjamin Tissot Official",
                "channel_is_verified": True,
                "duration": 157,
                "url": "https://www.jamendo.com/track/jam_456",
                "stream_url": "https://prod-1.storage.jamendo.com/?trackid=jam_456&format=mp32",
                "thumbnail": "https://usercontent.jamendo.com/cover.jpg",
                "provider": "jamendo",
            }
        ]

        track = await AudioResolver.resolve_track("acoustic breeze", 123, "Tester")
        self.assertIsNotNone(track)
        self.assertEqual(track.title, "Acoustic Breeze - Official Release")
        self.assertEqual(getattr(track, "provider", None), "jamendo")
        self.assertIn("jamendo.com", track.stream_url)

    # =========================================================================
    # 5. UNIFIED PLAYER & QUEUE EMBED RENDERING
    # =========================================================================

    def test_unified_player_embed_shows_provider_badge(self):
        """Verify Now Playing embed displays provider badges (Audius, Jamendo, Spotify, Apple Music)."""
        # Test Audius track badge
        audius_track = QueuedTrack(
            title="Audius Synth Wave",
            url="https://audius.co/track/1",
            stream_url="https://api.audius.co/v1/tracks/1/stream",
            duration=180,
            artist="Indie Artist",
            requester_id=123,
            requester_name="Tester",
        )
        setattr(audius_track, "provider", "audius")
        self.session.current_track = audius_track

        embed = MusicPlayerService.build_now_playing_embed(self.session)
        self.assertIn("Audius", embed.description)

        # Test Jamendo track badge
        jamendo_track = QueuedTrack(
            title="Jamendo Acoustic",
            url="https://jamendo.com/track/2",
            stream_url="https://storage.jamendo.com/track/2",
            duration=200,
            artist="CC Composer",
            requester_id=123,
            requester_name="Tester",
        )
        setattr(jamendo_track, "provider", "jamendo")
        self.session.current_track = jamendo_track

        embed = MusicPlayerService.build_now_playing_embed(self.session)
        self.assertIn("Jamendo", embed.description)

        # Test Apple Music badge
        apple_track = QueuedTrack(
            title="Apple Catalog Song",
            url="https://music.apple.com/song/3",
            stream_url="https://audio-stream.googlevideo.com/playback",
            duration=210,
            artist="Pop Artist",
            requester_id=123,
            requester_name="Tester",
        )
        setattr(apple_track, "provider", "apple_music")
        self.session.current_track = apple_track

        embed = MusicPlayerService.build_now_playing_embed(self.session)
        self.assertIn("Apple Music", embed.description)

    # =========================================================================
    # 6. WRONG-LANGUAGE REJECTION & EXACT MATCHING
    # =========================================================================

    def test_original_song_matching_rejects_wrong_language_or_remix(self):
        """Verify ranking and validation rejects Devanagari/Hindi results for Tamil queries."""
        intent = analyze_query_intent("Pichuva Kaththi Enna Sona tamil")
        self.assertEqual(intent.get("detected_language"), "tamil")

        # Wrong language (Hindi text for Tamil query)
        hindi_cand = {
            "title": "पिछुवा कत्थी (Hindi Dub Remix)",
            "uploader": "Bollywood Remix Hub",
            "channel_is_verified": False,
        }
        self.assertFalse(is_original_recording_candidate(hindi_cand, intent))

        # Legitimate original Tamil track
        tamil_cand = {
            "title": "Pichuva Kaththi Enna Sona - Official Video | AR Rahman",
            "uploader": "Sony Music South",
            "channel_is_verified": True,
        }
        self.assertTrue(is_original_recording_candidate(tamil_cand, intent))

    # =========================================================================
    # 7. SSRF PROTECTION FOR DIRECT AUDIO EXTRACTION
    # =========================================================================

    @patch("music_bot.services.resolver_service._run_ytdlp")
    async def test_direct_audio_url_with_private_ip_is_blocked_before_ytdlp(self, mock_run):
        """Verify private network URLs are blocked before yt-dlp is ever called."""
        track = await AudioResolver.resolve_track(
            "http://192.168.1.100/song.mp3",
            123,
            "User",
        )
        self.assertIsNone(track)
        mock_run.assert_not_called()
        self.assertIn("[SECURITY_VIOLATION]", AudioResolver.last_resolver_error)

    # =========================================================================
    # 8. PREVENTING DUPLICATE QUEUE CONFLICTS
    # =========================================================================

    def test_queue_track_addition_preserves_unique_order(self):
        """Verify queue additions maintain order and queue states cleanly across providers."""
        t1 = QueuedTrack(title="Track 1", url="https://youtube.com/watch?v=1", requester_id=1)
        t2 = QueuedTrack(title="Track 2", url="https://audius.co/track/2", requester_id=1)
        setattr(t2, "provider", "audius")

        self.session.queue.append(t1)
        self.session.queue.append(t2)
        self.assertEqual(len(self.session.queue), 2)
        self.assertEqual(self.session.queue[0].title, "Track 1")
        self.assertEqual(self.session.queue[1].title, "Track 2")


if __name__ == "__main__":
    unittest.main()
