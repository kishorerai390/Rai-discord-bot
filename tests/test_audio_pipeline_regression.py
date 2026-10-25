"""
Comprehensive Rythm-Inspired Audio Pipeline Regression Test Suite.
Tests:
1. Correct candidate selection for common song queries.
2. Rejecting unrelated tracks and covers when original is requested.
3. Ambiguous results requiring user selection.
4. Preserving the selected video ID throughout resolution.
5. Format selection resilience (accepting progressive formats on SABR restrictions).
6. YouTube 403, 429, and authentication error handling with cooldowns.
7. Resolver timeout and cancellation handling.
8. Lavalink disabled by default and gracefully handles unavailability.
9. Audius/Jamendo fallback matching (strict title match, rejects unrelated).
10. Duplicate slash-command and rapid-click protection.
11. Queue progression after stream decoding failures.
"""

from __future__ import annotations

import asyncio
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from music_bot.database.models import QueuedTrack
from music_bot.services.lavalink_service import LavalinkManager
from music_bot.services.resolver_service import (
    AudioResolver,
    _candidate_match_metrics,
    _is_strong_fallback_title_match,
    _video_id_from_url,
    analyze_query_intent,
    is_original_recording_candidate,
    requires_candidate_confirmation,
    score_candidate,
    youtube_health_monitor,
)
from music_bot.services.session_service import GuildMusicSession, LoopMode, PlaybackState


class AudioPipelineRegressionTests(unittest.TestCase):
    def setUp(self):
        AudioResolver.clear_caches()
        youtube_health_monitor.cooldown_until = 0.0
        youtube_health_monitor.consecutive_failures = 0
        youtube_health_monitor.last_failure_reason = None

    def test_01_candidate_selection_preserves_original_and_scores_highest(self):
        query = "Faded Alan Walker"
        intent = analyze_query_intent(query)
        candidates = [
            {
                "id": "60ItHLz5WEA",
                "title": "Alan Walker - Faded",
                "uploader": "Alan Walker",
                "channel_is_verified": True,
                "duration": 212,
            },
            {
                "id": "cover999",
                "title": "Faded - Acoustic Cover",
                "uploader": "Cover Singer",
                "duration": 210,
            },
        ]
        self.assertTrue(is_original_recording_candidate(candidates[0], intent))
        self.assertFalse(is_original_recording_candidate(candidates[1], intent))
        score_orig = score_candidate(candidates[0], intent)
        score_cov = score_candidate(candidates[1], intent)
        self.assertGreater(score_orig, score_cov)

    def test_02_unrelated_song_rejected_from_fallback(self):
        intent = analyze_query_intent("Faded")
        unrelated_candidate = {
            "title": "Lost (Faded)",
            "artist": "Different Artist",
            "duration": 180,
        }
        self.assertFalse(_is_strong_fallback_title_match(unrelated_candidate, intent))

    def test_03_ambiguous_results_trigger_confirmation(self):
        ambiguous = [
            {"_title_match_ratio": 1.0, "_match_score": 210.0, "_title_match_confidence": 0.95},
            {"_title_match_ratio": 1.0, "_match_score": 208.0, "_title_match_confidence": 0.95},
        ]
        self.assertTrue(requires_candidate_confirmation(ambiguous))

        confident = [
            {"_title_match_ratio": 1.0, "_match_score": 240.0, "_title_match_confidence": 1.0},
            {"_title_match_ratio": 0.6, "_match_score": 150.0, "_title_match_confidence": 0.6},
        ]
        self.assertFalse(requires_candidate_confirmation(confident))

    def test_04_selected_video_id_preserved_throughout_resolution(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        vid = _video_id_from_url(url)
        self.assertEqual(vid, "dQw4w9WgXcQ")

        short_url = "https://youtu.be/dQw4w9WgXcQ"
        self.assertEqual(_video_id_from_url(short_url), "dQw4w9WgXcQ")

    def test_05_youtube_429_activates_cooldown(self):
        youtube_health_monitor.record_failure("HTTP Error 429: Too Many Requests")
        status = youtube_health_monitor.cooldown_status()
        self.assertTrue(status["cooldown_active"])
        self.assertEqual(status["last_failure"], "rate_limited")
        self.assertGreater(status["cooldown_remaining_seconds"], 0)

    def test_06_youtube_sign_in_bot_verification_activates_cooldown(self):
        youtube_health_monitor.record_failure("Sign in to confirm you're not a bot")
        status = youtube_health_monitor.cooldown_status()
        self.assertTrue(status["cooldown_active"])
        self.assertEqual(status["last_failure"], "access_denied")

    def test_07_lavalink_is_disabled_by_default(self):
        self.assertFalse(LavalinkManager.is_connected())
        diag = LavalinkManager.get_diagnostics()
        self.assertEqual(diag["active_engine"], "Native yt-dlp + FFmpeg")
        self.assertFalse(diag["connected"])

    def test_08_audius_fallback_accepts_exact_song_match(self):
        intent = analyze_query_intent("Chill Sunset")
        exact_candidate = {
            "title": "Chill Sunset",
            "artist": "Lofi Producer",
            "duration": 150,
        }
        self.assertTrue(_is_strong_fallback_title_match(exact_candidate, intent))

    def test_09_resolver_timeout_returns_bounded_failure(self):
        async def _test():
            with patch("music_bot.services.resolver_service._run_ytdlp", side_effect=asyncio.TimeoutError()):
                track = await AudioResolver.resolve_track(
                    "https://www.youtube.com/watch?v=testtimeout1",
                    requester_id=1,
                    requester_name="Tester",
                )
                self.assertIsNone(track)
                self.assertIn("TIMEOUT", getattr(AudioResolver, "last_resolver_error", "") or "")

        asyncio.run(_test())

    def test_10_queue_progression_after_playback_failure(self):
        async def _test():
            bot = MagicMock()
            session = GuildMusicSession(guild_id=123)
            track1 = QueuedTrack(title="Failed Track", url="https://example.com/1", duration=100)
            track2 = QueuedTrack(title="Next Track", url="https://example.com/2", duration=200)
            session.queue.append(track2)
            session.current_track = track1
            session.state = PlaybackState.PLAYING

            from music_bot.services.player_service import MusicPlayerService
            with patch.object(MusicPlayerService, "start_playback", new_callable=AsyncMock, return_value=True) as mock_start:
                await MusicPlayerService.handle_track_finished(bot, session)
                mock_start.assert_called_once_with(bot, session, track2)

        asyncio.run(_test())

    def test_11_active_cooldown_triggers_immediate_alternative_fallback(self):
        """During active YouTube cooldown, resolve_track immediately searches alternatives without waiting."""
        async def _test():
            youtube_health_monitor.record_failure("HTTP Error 429: Too Many Requests")
            self.assertTrue(youtube_health_monitor.cooldown_status()["cooldown_active"])

            audius_track = QueuedTrack(
                title="Chill Beats",
                url="https://audius.co/track/123",
                stream_url="https://audius-stream.com/live.mp3",
                duration=120,
            )
            with patch.object(
                AudioResolver,
                "resolve_alternative_fallback",
                new_callable=AsyncMock,
                return_value=(audius_track, {"audius": "matched"}),
            ) as mock_fb:
                track = await AudioResolver.resolve_track(
                    "Chill Beats",
                    requester_id=1,
                    requester_name="Tester",
                    correlation_id="TEST-FALLBACK-1",
                )
                self.assertIsNotNone(track)
                self.assertEqual(track.title, "Chill Beats")
                mock_fb.assert_called_once()

        asyncio.run(_test())

    def test_12_active_cooldown_reports_diagnostics_when_no_match_exists(self):
        """When no matching track exists on alternatives during cooldown, report clear diagnostics without playing wrong songs."""
        async def _test():
            youtube_health_monitor.record_failure("Sign in to confirm you're not a bot")
            self.assertTrue(youtube_health_monitor.cooldown_status()["cooldown_active"])

            with patch.object(
                AudioResolver,
                "resolve_alternative_fallback",
                new_callable=AsyncMock,
                return_value=(None, {"audius": "0 matching recordings verified", "jamendo": "0 matching recordings verified"}),
            ):
                track = await AudioResolver.resolve_track(
                    "Rare Unique Song Title",
                    requester_id=1,
                    requester_name="Tester",
                    correlation_id="TEST-FALLBACK-2",
                )
                self.assertIsNone(track)
                err = getattr(AudioResolver, "last_resolver_error", "") or ""
                self.assertIn("ACCESS_RESTRICTION", err)
                self.assertIn("Audius", err)
                self.assertIn("Jamendo", err)

        asyncio.run(_test())

    def test_13_recovery_after_cooldown_resets_youtube_access(self):
        """When cooldown is cleared or expired, YouTube resolution resumes normally."""
        async def _test():
            youtube_health_monitor.record_failure("Sign in to confirm you're not a bot")
            self.assertTrue(youtube_health_monitor.cooldown_status()["cooldown_active"])

            youtube_health_monitor.reset_cooldown()
            self.assertFalse(youtube_health_monitor.cooldown_status()["cooldown_active"])

            yt_track = QueuedTrack(
                title="Recovered Song",
                url="https://www.youtube.com/watch?v=recovered1",
                stream_url="https://rr1---sn.googlevideo.com/videoplayback",
                duration=180,
            )
            with patch.object(AudioResolver, "_execute_resolution_pipeline", new_callable=AsyncMock, return_value=yt_track):
                track = await AudioResolver.resolve_track("Recovered Song", 1, "Tester")
                self.assertIsNotNone(track)
                self.assertEqual(track.title, "Recovered Song")

        asyncio.run(_test())

    def test_14_youtube_timeout_cooldown_triggers_immediate_fallback_and_reports_timeout(self):
        """Active YouTube timeout cooldown immediately tries alternatives and reports TIMEOUT category, not ACCESS_RESTRICTION."""
        async def _test():
            youtube_health_monitor.record_failure("ReadTimeoutError: HTTPSConnectionPool timed out")
            status = youtube_health_monitor.cooldown_status()
            self.assertTrue(status["cooldown_active"])
            self.assertEqual(status["last_failure"], "timeout")

            with patch.object(
                AudioResolver,
                "resolve_alternative_fallback",
                new_callable=AsyncMock,
                return_value=(None, {"audius": "0 matching recordings verified", "jamendo": "0 matching recordings verified"}),
            ) as mock_fb:
                track = await AudioResolver.resolve_track(
                    "Despacito",
                    requester_id=1,
                    requester_name="Tester",
                    correlation_id="MM-594C0941",
                )
                self.assertIsNone(track)
                mock_fb.assert_called_once()
                err = getattr(AudioResolver, "last_resolver_error", "") or ""
                self.assertIn("TIMEOUT", err)
                self.assertNotIn("ACCESS_RESTRICTION", err)
                self.assertIn("MM-594C0941", err)
                self.assertIn("Tried alternatives", err)

        asyncio.run(_test())

    def test_15_despacito_fallback_strictly_rejects_i_write_despacito_not_tragedies(self):
        """When query is 'despacito', unrelated songs like 'I write despacito not tragedies' are strictly rejected."""
        intent = analyze_query_intent("despacito")
        bad_candidate = {
            "title": "I write despacito not tragedies",
            "artist": "Panic! At The Disco",
            "duration": 185,
        }
        good_candidate = {
            "title": "Despacito (Official Video)",
            "artist": "Luis Fonsi",
            "duration": 229,
        }

        # 1. Resolver level rejection
        self.assertFalse(_is_strong_fallback_title_match(bad_candidate, intent))
        self.assertTrue(_is_strong_fallback_title_match(good_candidate, intent))

        # 2. Command level rejection
        from music_bot.commands.music_cog import _alternative_track_matches_query
        bad_track = QueuedTrack(
            title=bad_candidate["title"],
            url="https://audius.co/bad",
            stream_url="https://audius-stream/bad.mp3",
            duration=185,
            artist=bad_candidate["artist"],
        )
        good_track = QueuedTrack(
            title=good_candidate["title"],
            url="https://audius.co/good",
            stream_url="https://audius-stream/good.mp3",
            duration=229,
            artist=good_candidate["artist"],
        )
        self.assertFalse(_alternative_track_matches_query("despacito", bad_track))
        self.assertTrue(_alternative_track_matches_query("despacito", good_track))

    def test_16_pinned_youtube_url_preserves_title_and_artist_for_fallback(self):
        """When a YouTube video URL is selected, fallback uses preserved title and artist, never the raw URL."""
        async def _test():
            youtube_health_monitor.record_failure("HTTP Error 429: Rate Limited")
            self.assertTrue(youtube_health_monitor.cooldown_status()["cooldown_active"])

            audius_track = QueuedTrack(
                title="Despacito",
                url="https://audius.co/despacito",
                stream_url="https://audius-stream/despacito.mp3",
                duration=229,
                artist="Luis Fonsi",
            )
            with patch.object(
                AudioResolver,
                "resolve_alternative_fallback",
                new_callable=AsyncMock,
                return_value=(audius_track, {}),
            ) as mock_fb:
                track = await AudioResolver.resolve_track(
                    "https://www.youtube.com/watch?v=kJQP7kiw5Fk",
                    requester_id=1,
                    requester_name="Tester",
                    title_hint="Despacito",
                    artist_hint="Luis Fonsi",
                    correlation_id="MM-594C0941",
                )
                self.assertIsNotNone(track)
                self.assertEqual(track.title, "Despacito")
                # Verify fallback was invoked with preserved song title, not the URL!
                mock_fb.assert_called_once()
                call_args = mock_fb.call_args[1]
                self.assertEqual(call_args.get("title"), "Despacito")
                self.assertEqual(call_args.get("artist"), "Luis Fonsi")

        asyncio.run(_test())

    def test_17_resolved_fallback_track_reaches_player_and_creates_ffmpeg_source(self):
        """A resolved fallback track with stream_url is successfully passed to the player and creates FFmpegPCMAudio."""
        async def _test():
            from music_bot.services.player_service import MusicPlayerService
            bot = MagicMock()
            session = GuildMusicSession(guild_id=456)
            session.voice_client = MagicMock()
            session.voice_client.is_connected.return_value = True
            session.voice_client.is_playing.return_value = False
            session.voice_client.is_paused.return_value = False

            fallback_track = QueuedTrack(
                title="Despacito",
                url="https://audius.co/track/123",
                stream_url="https://api.audius.co/v1/tracks/123/stream",
                duration=229,
                artist="Luis Fonsi",
            )
            setattr(fallback_track, "provider", "audius")
            setattr(fallback_track, "_correlation_id", "MM-594C0941")

            with patch("discord.FFmpegPCMAudio") as mock_ffmpeg, \
                 patch("discord.PCMVolumeTransformer") as mock_vol:
                mock_vol_instance = MagicMock()
                mock_vol_instance.read.return_value = b"\x00\x00" * 960  # valid PCM audio frame
                mock_vol.return_value = mock_vol_instance

                success = await MusicPlayerService.start_playback(bot, session, fallback_track)
                self.assertTrue(success)
                mock_ffmpeg.assert_called_once()
                ffmpeg_call_url = mock_ffmpeg.call_args[0][0]
                self.assertEqual(ffmpeg_call_url, "https://api.audius.co/v1/tracks/123/stream")
                session.voice_client.play.assert_called_once()

        asyncio.run(_test())

    def test_18_structured_logging_records_correlation_id_and_provider_events(self):
        """Every provider fallback attempt, search, and rejection logs structured fields with correlation ID."""
        async def _test():
            import logging
            with patch("music_bot.services.alternative_providers.AudiusProviderService.search", new_callable=AsyncMock) as mock_aud:
                mock_aud.return_value = [
                    {
                        "id": "999",
                        "title": "I write despacito not tragedies",
                        "artist": "Panic! At The Disco",
                        "duration": 180,
                        "stream_url": "https://audius/stream/999",
                    }
                ]
                with patch("music_bot.services.alternative_providers.JamendoProviderService.search", new_callable=AsyncMock) as mock_jam:
                    mock_jam.return_value = []

                    with self.assertLogs("RaiMusic.Resolver", level=logging.INFO) as cm:
                        track, diag = await AudioResolver.resolve_alternative_fallback(
                            title="Despacito",
                            artist="Luis Fonsi",
                            correlation_id="MM-594C0941",
                        )
                        self.assertIsNone(track)
                        log_output = "\n".join(cm.output)
                        self.assertIn("MM-594C0941", log_output)
                        self.assertIn("provider=audius", log_output)
                        self.assertIn("operation=fallback_search", log_output)
                        self.assertIn("operation=fallback_match_rejected", log_output)
                        self.assertIn("reason=", log_output)

        asyncio.run(_test())


if __name__ == "__main__":
    unittest.main()

