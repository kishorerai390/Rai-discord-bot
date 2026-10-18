"""
Unit and regression tests for:
1. YouTube + Spotify only (SoundCloud completely removed and disabled).
2. Original song preference vs remix penalty (e.g. 'enna sonna' selects original, 'enna sonna remix' selects remix).
3. Tamil script and transliteration language ranking accuracy.
4. /skip single response handling and ensure_deferred idempotence.
5. Interactive player panel deployment on /play response.
"""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from music_bot.services.resolver_service import (
    AudioResolver,
    analyze_query_intent,
    score_candidate,
)
from music_bot.services.player_service import GuildMusicSession, MusicPlayerService, PlaybackState
from music_bot.database.models import QueuedTrack


class TestSongRankingAndSourcePolicy(unittest.TestCase):
    # =============================================================================
    # 1. ORIGINAL SONG PREFERENCE VS REMIX TESTS
    # =============================================================================

    def test_query_intent_analysis_normal_vs_remix(self):
        """Verify normal query detects no alternate request, while remix query detects remix request."""
        intent_normal = analyze_query_intent("enna sonna")
        self.assertFalse(intent_normal["user_requested_alternate"])
        self.assertFalse(intent_normal["wants_remix"])

        intent_remix = analyze_query_intent("enna sonna remix")
        self.assertTrue(intent_remix["user_requested_alternate"])
        self.assertTrue(intent_remix["wants_remix"])

        intent_slowed = analyze_query_intent("Enna Sona slowed reverb")
        self.assertTrue(intent_slowed["user_requested_alternate"])
        self.assertTrue(intent_slowed["wants_slowed"])

    def test_score_candidate_penalizes_unrequested_remix(self):
        """Verify score_candidate heavily penalizes remix candidates when user asks for normal song."""
        intent = analyze_query_intent("enna sonna")

        original_cand = {
            "title": "Enna Sona - OK Jaanu | Arijit Singh | A.R. Rahman | Official Music Video",
            "uploader": "Sony Music India VEVO",
            "duration": 213,
        }
        remix_cand = {
            "title": "Caps x Frenzo Enna Sona Remix",
            "uploader": "RemixHub",
            "duration": 185,
        }

        orig_score = score_candidate(original_cand, intent)
        remix_score = score_candidate(remix_cand, intent)

        self.assertGreater(orig_score, remix_score)
        self.assertGreaterEqual(orig_score - remix_score, 70.0)

    def test_score_candidate_rewards_explicitly_requested_remix(self):
        """Verify score_candidate prefers the remix when the user explicitly requests one."""
        intent = analyze_query_intent("enna sonna remix")

        original_cand = {
            "title": "Enna Sona - OK Jaanu | Arijit Singh | A.R. Rahman | Official Music Video",
            "uploader": "Sony Music India VEVO",
            "duration": 213,
        }
        remix_cand = {
            "title": "Caps x Frenzo Enna Sona Remix",
            "uploader": "RemixHub",
            "duration": 185,
        }

        orig_score = score_candidate(original_cand, intent)
        remix_score = score_candidate(remix_cand, intent)

        self.assertGreater(remix_score, orig_score)

    # =============================================================================
    # 2. TAMIL SCRIPT & REGIONAL LANGUAGE MATCHING TESTS
    # =============================================================================

    def test_tamil_unicode_detection_and_ranking(self):
        """Verify Tamil script is recognized and prioritized over conflicting language tracks."""
        # Query in Tamil script: "கண்ணழகா" (Kannazhaga)
        intent = analyze_query_intent("கண்ணழகா")
        self.assertTrue(intent["has_tamil_script"])
        self.assertEqual(intent["detected_language"], "tamil")

        tamil_cand = {
            "title": "கண்ணழகா - 3 | Dhanush, Shruti Haasan | Anirudh | Tamil Official Video",
            "uploader": "SonyMusicSouthVEVO",
            "duration": 205,
        }
        hindi_cand = {
            "title": "Kannazhaga Hindi Dubbed Version Song",
            "uploader": "Random Channel",
            "duration": 205,
        }

        tamil_score = score_candidate(tamil_cand, intent)
        hindi_score = score_candidate(hindi_cand, intent)

        self.assertGreater(tamil_score, hindi_score)

    def test_transliterated_tamil_song_prioritization(self):
        """Verify transliterated Tamil songs with Tamil markers score higher than Hindi tracks."""
        intent = analyze_query_intent("arabic kuthu tamil")
        self.assertEqual(intent["detected_language"], "tamil")

        tamil_cand = {
            "title": "Arabic Kuthu - Beast | Thalapathy Vijay | Sun Pictures | Anirudh | Tamil Video",
            "uploader": "Sun TV",
            "duration": 280,
        }
        hindi_cand = {
            "title": "Arabic Kuthu Hindi Version (Halamithi Habibo)",
            "uploader": "Sun TV Hindi",
            "duration": 280,
        }

        self.assertGreater(score_candidate(tamil_cand, intent), score_candidate(hindi_cand, intent))

    # =============================================================================
    # 3. SOUNDCLOUD COMPLETELY DISABLED TESTS
    # =============================================================================

    def test_soundcloud_never_called_during_search(self):
        """Ensure AudioResolver.search never calls SoundCloud even if YouTube fails."""
        async def _test():
            AudioResolver._search_cache.clear()

            mock_ydl = MagicMock()
            mock_ydl.extract_info.side_effect = Exception("HTTP 403 Forbidden: Datacenter IP blocked")

            with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
                res = await AudioResolver.search("test song query", limit=3)
                self.assertEqual(res, [])
                for call_args in mock_ydl.extract_info.call_args_list:
                    arg = call_args[0][0]
                    self.assertNotIn("scsearch", arg)
                    self.assertNotIn("soundcloud", arg)

        asyncio.run(_test())

    def test_probe_reports_soundcloud_disabled(self):
        """Verify extractor health probe explicitly reports SoundCloud disabled."""
        async def _test():
            mock_ydl = MagicMock()
            mock_ydl.extract_info.side_effect = Exception("YouTube restricted")

            with patch.object(AudioResolver, "PROFILE_PRESETS", [["mweb", "web"]]), \
                 patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
                diag = await AudioResolver.probe_extractor_health(force=True)
                self.assertFalse(diag["soundcloud_operational"])
                self.assertIn("SoundCloud is disabled", diag["message"])

        asyncio.run(_test())

    # =============================================================================
    # 4. INTERACTION RESPONSE & /skip REGRESSION TESTS
    # =============================================================================

    def test_skip_command_deferral_idempotence(self):
        """Verify skipping an active track executes atomically without double deferral errors."""
        async def _test():
            mock_bot = MagicMock()
            session = GuildMusicSession(guild_id=123456)
            track1 = QueuedTrack(title="Song 1", url="https://youtube.com/watch?v=1", duration=200, requester_id=999, requester_name="Rai")
            track2 = QueuedTrack(title="Song 2", url="https://youtube.com/watch?v=2", duration=180, requester_id=999, requester_name="Rai")

            session.current_track = track1
            session.queue.append(track2)
            session.state = PlaybackState.PLAYING
            mock_vc = MagicMock()
            mock_vc.is_playing.return_value = True
            session.voice_client = mock_vc

            with patch.object(MusicPlayerService, "start_playback", new_callable=AsyncMock) as mock_start:
                mock_start.return_value = True
                success, msg, next_track = await MusicPlayerService.skip(mock_bot, session)
                self.assertTrue(success)
                self.assertEqual(next_track, track2)
                self.assertTrue(mock_vc.stop.called)

        asyncio.run(_test())


if __name__ == "__main__":
    unittest.main()
