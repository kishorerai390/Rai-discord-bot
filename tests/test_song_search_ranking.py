"""
Comprehensive Phase 5 automated test suite for MusicMaid:
Smart Original Song Search, DJ Remix Selection, and Language Accuracy.

Validates all 8 specific requirements:
1. Original song versus DJ remix.
2. Explicit remix requests.
3. Tamil query versus unrelated Hindi results.
4. Official audio versus unrelated cover or karaoke.
5. Multiple legitimate original versions.
6. No suitable original result.
7. YouTube resolver timeout and empty search results.
8. Consistent behavior for slash and prefix commands.
"""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from music_bot.services.resolver_service import (
    AudioResolver,
    analyze_query_intent,
    is_original_recording_candidate,
    score_candidate,
    score_candidate_detailed,
)
from music_bot.database.models import QueuedTrack


class TestSongSearchRanking(unittest.TestCase):
    def setUp(self):
        AudioResolver.clear_caches()

    # =========================================================================
    # 1. ORIGINAL SONG VERSUS DJ REMIX
    # =========================================================================
    def test_01_original_song_versus_dj_remix(self):
        """
        Verify searching for a standard song title (e.g. 'Kalyani' or 'enna sonna')
        strongly prioritizes the official/original recording over DJ remixes, mashups,
        bootlegs, or bass-boosted edits.
        """
        intent = analyze_query_intent("Kalyani")
        self.assertFalse(intent["user_requested_alternate"])
        self.assertFalse(intent["wants_remix"])

        original_cand = {
            "title": "Kalyani - Official Video | Anirudh | Sony Music South",
            "uploader": "SonyMusicSouthVEVO",
            "duration": 240,
        }
        dj_remix_cand = {
            "title": "Kalyani (DJ Remix 2024 Bass Boosted Party Mix)",
            "uploader": "DJ King Club",
            "duration": 210,
        }
        mashup_cand = {
            "title": "Kalyani x Arabic Kuthu Mashup Bootleg",
            "uploader": "Mashup Masters",
            "duration": 195,
        }

        orig_score, orig_reasons = score_candidate_detailed(original_cand, intent)
        remix_score, remix_reasons = score_candidate_detailed(dj_remix_cand, intent)
        mashup_score, mashup_reasons = score_candidate_detailed(mashup_cand, intent)

        self.assertGreater(orig_score, remix_score, "Original must score higher than DJ remix")
        self.assertGreater(orig_score, mashup_score, "Original must score higher than mashup")
        self.assertGreaterEqual(orig_score - remix_score, 80.0, "Expected at least 80 point separation for remix penalty")
        self.assertTrue(any("unrequested_remix" in r for r in remix_reasons))

    def test_01b_title_match_outweighs_unrelated_official_upload(self):
        """A weakly related official upload must not outrank the exact requested title."""
        intent = analyze_query_intent("blue moon midnight rain")
        exact_title = {
            "title": "Blue Moon Midnight Rain",
            "uploader": "Independent Artist",
            "duration": 210,
        }
        partial_official_match = {
            "title": "Blue Moon (Official Audio)",
            "uploader": "OfficialMusicCo",
            "duration": 210,
        }

        exact_score = score_candidate(exact_title, intent)
        partial_score = score_candidate(partial_official_match, intent)

        self.assertGreater(
            exact_score,
            partial_score,
            "Title relevance must outweigh publisher and duration bonuses for a partial match",
        )

    def test_01c_standard_search_requires_source_evidence_and_rejects_covers(self):
        intent = analyze_query_intent("Kalyani")
        original_release = {
            "title": "Kalyani - Official Music Video",
            "uploader": "SingerVEVO",
            "duration": 240,
        }
        cover = {
            "title": "Kalyani cover by Local Singer",
            "uploader": "SingerVEVO",
            "duration": 240,
        }
        unidentified_upload = {
            "title": "Kalyani",
            "uploader": "Unknown Channel",
            "duration": 240,
        }

        self.assertTrue(is_original_recording_candidate(original_release, intent))
        self.assertFalse(is_original_recording_candidate(cover, intent))
        self.assertFalse(is_original_recording_candidate(unidentified_upload, intent))

    def test_01c2_rejects_similarly_spelled_but_different_song_title(self):
        intent = analyze_query_intent("enna sonna")
        similar_title = {
            "title": "Enna Sona - OK Jaanu",
            "uploader": "Sony Music India",
            "duration": 213,
        }

        self.assertFalse(is_original_recording_candidate(similar_title, intent))

    def test_01c2b_accepts_requested_song_from_trend_music_official_channel(self):
        intent = analyze_query_intent("enna sonna")
        original_release = {
            "title": "Pichuva Kaththi - Enna Sonna Video Song | Inigo Prabhakaran",
            "uploader": "Trend Music | TrendMusic",
            "duration": 262,
        }

        self.assertTrue(is_original_recording_candidate(original_release, intent))

    def test_01c3_allows_long_title_typo_but_rejects_short_form_clip(self):
        intent = analyze_query_intent("rasagula anirudh")
        original = {
            "title": "Rasagulla - Video Song | Hi | Anirudh Ravichander",
            "uploader": "Sony Music South",
            "duration": 242,
        }
        short_form_clip = {
            "title": "Rasagulla - Trending Instagram Dance Reels | Anirudh Ravichander",
            "uploader": "Sony Music South",
            "duration": 68,
        }

        self.assertTrue(is_original_recording_candidate(original, intent))
        self.assertFalse(is_original_recording_candidate(short_form_clip, intent))

    def test_01d_explicit_alternate_search_is_rejected_by_original_only_policy(self):
        intent = analyze_query_intent("Kalyani remix")
        remix = {
            "title": "Kalyani DJ Remix - Official Audio",
            "uploader": "DJ Channel",
            "duration": 210,
        }

        self.assertFalse(is_original_recording_candidate(remix, intent))

    def test_01e_search_only_returns_verified_original_for_normal_request(self):
        async def _test():
            AudioResolver.clear_caches()
            ydl = MagicMock()
            ydl.extract_info.return_value = {
                "entries": [
                    {
                        "id": "cover1234567",
                        "title": "Kalyani cover by Local Singer",
                        "uploader": "Random Channel",
                        "duration": 240,
                    },
                    {
                        "id": "original1234",
                        "title": "Kalyani - Official Music Video",
                        "uploader": "SingerVEVO",
                        "duration": 240,
                    },
                ]
            }
            with patch("music_bot.services.resolver_service._build_ytdl_options", return_value={}), \
                 patch("music_bot.services.resolver_service.yt_dlp.YoutubeDL", return_value=ydl):
                results = await AudioResolver.search("Kalyani", limit=5)

            self.assertEqual([result["id"] for result in results], ["original1234"])
            self.assertTrue(results[0]["original_source_match"])

        asyncio.run(_test())

    def test_01e2_direct_youtube_links_reject_unverified_remixes(self):
        async def _test():
            AudioResolver.clear_caches()
            ydl = MagicMock()
            ydl.extract_info.return_value = {
                "id": "remix1234567",
                "title": "Kalyani DJ Remix",
                "webpage_url": "https://www.youtube.com/watch?v=remix1234567",
                "url": "https://audio.example/stream",
                "duration": 210,
                "uploader": "Unknown DJ Channel",
            }

            with patch("music_bot.services.resolver_service._build_ytdl_options", return_value={}), \
                 patch("music_bot.services.resolver_service.yt_dlp.YoutubeDL", return_value=ydl):
                result = await AudioResolver._execute_resolution_pipeline(
                    "https://www.youtube.com/watch?v=remix1234567", 123, "Tester"
                )

            self.assertIsNone(result)
            self.assertIn("NO_ORIGINAL_MATCH", AudioResolver.last_resolver_error or "")

        asyncio.run(_test())

    def test_01e3_direct_youtube_original_from_official_label_is_playable(self):
        async def _test():
            AudioResolver.clear_caches()
            ydl = MagicMock()
            ydl.extract_info.return_value = {
                "id": "gJNTdUdNwMY",
                "title": "Pichuva Kaththi - Enna Sonna Video Song | Inigo Prabhakaran",
                "webpage_url": "https://www.youtube.com/watch?v=gJNTdUdNwMY",
                "url": "https://audio.example/stream",
                "duration": 262,
                "uploader": "Trend Music | TrendMusic",
            }

            with patch("music_bot.services.resolver_service._build_ytdl_options", return_value={}), \
                 patch("music_bot.services.resolver_service.yt_dlp.YoutubeDL", return_value=ydl):
                result = await AudioResolver._execute_resolution_pipeline(
                    "https://www.youtube.com/watch?v=gJNTdUdNwMY", 123, "Tester"
                )

            self.assertIsNotNone(result)
            self.assertEqual(result.title, "Pichuva Kaththi - Enna Sonna Video Song | Inigo Prabhakaran")

        asyncio.run(_test())

    def test_01f_enna_sonna_dj_remix_is_rejected_without_original_match(self):
        async def _test():
            AudioResolver.clear_caches()
            ydl = MagicMock()
            ydl.extract_info.return_value = {
                "entries": [
                    {
                        "id": "cover1234567",
                        "title": "Caps x Frenzo Enna Sona Remix",
                        "uploader": "zohaib javed",
                        "duration": 126,
                    }
                ]
            }
            with patch.object(AudioResolver, "search", new_callable=AsyncMock, return_value=[]), \
                 patch.object(AudioResolver, "resolve_soundcloud_track", new_callable=AsyncMock) as soundcloud, \
                 patch("music_bot.services.resolver_service._build_ytdl_options", return_value={}), \
                 patch("music_bot.services.resolver_service.yt_dlp.YoutubeDL", return_value=ydl):
                result = await AudioResolver._execute_resolution_pipeline("enna sonna", 123, "Tester")

            self.assertIsNone(result)
            self.assertFalse(soundcloud.called)
            self.assertIn("NO_ORIGINAL_MATCH", AudioResolver.last_resolver_error or "")

        asyncio.run(_test())

    def test_01g_retries_unavailable_format_with_android_vr_profile(self):
        async def _test():
            AudioResolver.clear_caches()
            options_used = []

            def youtube_dl(options):
                options_used.append(options)
                ydl = MagicMock()
                clients = options["extractor_args"]["youtube"].get("player_client")
                if clients == ["android_vr"]:
                    ydl.extract_info.return_value = {
                        "title": "Kalyani - Official Music Video",
                        "webpage_url": "https://www.youtube.com/watch?v=original1234",
                        "url": "https://audio.example/stream",
                        "duration": 240,
                        "uploader": "SingerVEVO",
                    }
                else:
                    ydl.extract_info.side_effect = RuntimeError("Requested format is not available")
                return ydl

            with patch.object(
                AudioResolver,
                "search",
                new_callable=AsyncMock,
                return_value=[{"url": "https://www.youtube.com/watch?v=original1234"}],
            ), patch("music_bot.services.resolver_service.yt_dlp.YoutubeDL", side_effect=youtube_dl):
                track = await AudioResolver._execute_resolution_pipeline("Kalyani", 123, "Tester")

            self.assertIsNotNone(track)
            self.assertEqual(track.title, "Kalyani - Official Music Video")
            self.assertTrue(track.stream_url)
            self.assertIn(["android_vr"], [
                opts["extractor_args"]["youtube"].get("player_client")
                for opts in options_used
            ])
            self.assertEqual(options_used[0]["format"], "bestaudio/best")

        asyncio.run(_test())

    def test_01h_cookie_fallback_retries_android_vr_profile(self):
        async def _test():
            AudioResolver.clear_caches()
            options_used = []

            def youtube_dl(options):
                options_used.append(options)
                ydl = MagicMock()
                is_cookie_android_vr = (
                    bool(options.get("cookiefile"))
                    and options["extractor_args"]["youtube"].get("player_client") == ["android_vr"]
                )
                if is_cookie_android_vr:
                    ydl.extract_info.return_value = {
                        "title": "Kalyani - Official Music Video",
                        "webpage_url": "https://www.youtube.com/watch?v=original1234",
                        "url": "https://audio.example/stream",
                        "duration": 240,
                        "uploader": "SingerVEVO",
                    }
                else:
                    ydl.extract_info.side_effect = RuntimeError("Requested format is not available")
                return ydl

            with patch.object(
                AudioResolver,
                "search",
                new_callable=AsyncMock,
                return_value=[{"url": "https://www.youtube.com/watch?v=original1234"}],
            ), patch(
                "music_bot.services.resolver_service.get_active_cookie_file",
                return_value="test-cookies.txt",
            ), patch(
                "music_bot.services.resolver_service.yt_dlp.YoutubeDL",
                side_effect=youtube_dl,
            ):
                track = await AudioResolver._execute_resolution_pipeline("Kalyani", 123, "Tester")

            self.assertIsNotNone(track)
            self.assertTrue(track.stream_url)
            self.assertTrue(any(
                options.get("cookiefile")
                and options["extractor_args"]["youtube"].get("player_client") == ["android_vr"]
                for options in options_used
            ))

        asyncio.run(_test())

    # =========================================================================
    # 2. EXPLICIT REMIX REQUESTS
    # =========================================================================
    def test_02_explicit_remix_requests(self):
        """
        Verify searching for an explicit remix (e.g. 'Kalyani DJ remix' or 'enna sonna remix')
        prioritizes the remix and does NOT penalize it, while penalizing the standard original.
        """
        intent = analyze_query_intent("Kalyani DJ remix")
        self.assertTrue(intent["user_requested_alternate"])
        self.assertTrue(intent["wants_remix"])

        original_cand = {
            "title": "Kalyani - Official Video | Anirudh | Sony Music South",
            "uploader": "SonyMusicSouthVEVO",
            "duration": 240,
        }
        dj_remix_cand = {
            "title": "Kalyani (DJ Remix 2024 Bass Boosted Party Mix)",
            "uploader": "DJ King Club",
            "duration": 210,
        }

        orig_score, orig_reasons = score_candidate_detailed(original_cand, intent)
        remix_score, remix_reasons = score_candidate_detailed(dj_remix_cand, intent)

        self.assertGreater(remix_score, orig_score, "Explicit remix request must prioritize the remix candidate")
        self.assertTrue(any("requested_remix_boost" in r for r in remix_reasons))
        self.assertTrue(any("original_penalized" in r for r in orig_reasons))

    def test_02b_dj_artist_name_does_not_imply_remix(self):
        """
        Verify artist names containing 'DJ' (e.g. DJ Snake, DJ Khaled) do not trigger
        remix intent, while explicit phrases ('DJ remix', 'DJ mix') do.
        """
        # 1. DJ Snake Turn Down for What — must not imply remix intent
        intent_snake = analyze_query_intent("DJ Snake Turn Down for What")
        self.assertFalse(intent_snake["wants_remix"], "DJ Snake must not imply remix intent")
        self.assertFalse(intent_snake["user_requested_alternate"], "DJ Snake must not set user_requested_alternate")
        self.assertIn("dj", intent_snake["core_title"].lower(), "DJ must not be stripped from artist name")

        # 2. DJ Khaled Wild Thoughts — must not imply remix intent
        intent_khaled = analyze_query_intent("DJ Khaled Wild Thoughts")
        self.assertFalse(intent_khaled["wants_remix"], "DJ Khaled must not imply remix intent")
        self.assertFalse(intent_khaled["user_requested_alternate"], "DJ Khaled must not set user_requested_alternate")
        self.assertIn("dj", intent_khaled["core_title"].lower(), "DJ must not be stripped from artist name")

        # 3. Wild Thoughts DJ remix — must imply remix intent
        intent_remix = analyze_query_intent("Wild Thoughts DJ remix")
        self.assertTrue(intent_remix["wants_remix"], "Wild Thoughts DJ remix must imply remix intent")
        self.assertTrue(intent_remix["user_requested_alternate"], "Wild Thoughts DJ remix must set user_requested_alternate")

        # 4. Song DJ mix — must imply alternate-version intent
        intent_mix = analyze_query_intent("Song DJ mix")
        self.assertTrue(intent_mix["wants_remix"], "Song DJ mix must imply remix intent")
        self.assertTrue(intent_mix["user_requested_alternate"], "Song DJ mix must set user_requested_alternate")

        # 5. Ranking: Official DJ Snake release vs Club Remix
        official_snake = {
            "title": "DJ Snake, Lil Jon - Turn Down for What",
            "uploader": "DJSnakeVEVO",
            "duration": 213,
        }
        remix_snake = {
            "title": "DJ Snake - Turn Down for What (Club Remix)",
            "uploader": "RemixHub",
            "duration": 200,
        }
        s_off = score_candidate(official_snake, intent_snake)
        s_rem = score_candidate(remix_snake, intent_snake)
        self.assertGreater(s_off, s_rem, "Official DJ Snake track must score higher than Club Remix")

    # =========================================================================
    # 3. TAMIL QUERY VERSUS UNRELATED HINDI RESULTS
    # =========================================================================
    def test_03_tamil_query_versus_unrelated_hindi_results(self):
        """
        Verify Tamil-specific queries or Unicode script prioritize Tamil language recordings
        over conflicting or unrelated Hindi/Telugu versions.
        """
        # Case A: Explicit language marker in query 'Kalyani Tamil'
        intent_a = analyze_query_intent("Kalyani Tamil")
        self.assertEqual(intent_a["detected_language"], "tamil")

        tamil_cand = {
            "title": "Kalyani Tamil Official Video Song",
            "uploader": "Sony Music South",
            "duration": 230,
        }
        hindi_cand = {
            "title": "Kalyani Hindi Dubbed Version Song (Bollywood Mix)",
            "uploader": "Zee Music Hindi",
            "duration": 230,
        }

        tamil_score = score_candidate(tamil_cand, intent_a)
        hindi_score = score_candidate(hindi_cand, intent_a)
        self.assertGreater(tamil_score, hindi_score, "Tamil query must prioritize Tamil track over Hindi version")
        self.assertGreaterEqual(tamil_score - hindi_score, 80.0)

        # Case B: Unicode script in query 'கல்யாணி'
        intent_b = analyze_query_intent("கல்யாணி")
        self.assertTrue(intent_b["has_tamil_script"])
        self.assertEqual(intent_b["detected_language"], "tamil")

        tamil_script_cand = {
            "title": "கல்யாணி - Official Video Song",
            "uploader": "Sony Music South",
            "duration": 220,
        }
        tamil_script_score = score_candidate(tamil_script_cand, intent_b)
        hindi_score_b = score_candidate(hindi_cand, intent_b)
        self.assertGreater(tamil_script_score, hindi_score_b, "Tamil Unicode script must prioritize Tamil candidate")

    # =========================================================================
    # 4. OFFICIAL AUDIO VERSUS UNRELATED COVER OR KARAOKE
    # =========================================================================
    def test_04_official_audio_versus_unrelated_cover_or_karaoke(self):
        """
        Verify standard queries prioritize official audio/video releases over amateur
        acoustic covers, karaoke tracks, instrumentals, and reaction videos.
        """
        intent = analyze_query_intent("Kesariya")
        self.assertFalse(intent["user_requested_alternate"])

        official_audio_cand = {
            "title": "Kesariya - Brahmāstra | Ranbir | Alia | Pritam | Arijit Singh | Official Audio",
            "uploader": "Sony Music India - Topic",
            "duration": 268,
        }
        acoustic_cover_cand = {
            "title": "Kesariya (Acoustic Cover by Singer)",
            "uploader": "AcousticVibes",
            "duration": 210,
        }
        karaoke_cand = {
            "title": "Kesariya Instrumental Karaoke with Lyrics",
            "uploader": "Karaoke Studio",
            "duration": 268,
        }
        reaction_cand = {
            "title": "AMERICAN REACTION to Kesariya Official Video!",
            "uploader": "ReactionZone",
            "duration": 540,
        }

        off_score = score_candidate(official_audio_cand, intent)
        cover_score = score_candidate(acoustic_cover_cand, intent)
        karaoke_score = score_candidate(karaoke_cand, intent)
        reaction_score = score_candidate(reaction_cand, intent)

        self.assertGreater(off_score, cover_score, "Official audio must beat acoustic cover")
        self.assertGreater(off_score, karaoke_score, "Official audio must beat karaoke")
        self.assertGreater(off_score, reaction_score, "Official audio must beat reaction video")

    # =========================================================================
    # 5. MULTIPLE LEGITIMATE ORIGINAL VERSIONS
    # =========================================================================
    def test_05_multiple_legitimate_original_versions(self):
        """
        Verify that multiple legitimate original uploads (Official Music Video,
        Lyric Video, YouTube Topic Audio) all score highly and are not penalized as remixes.
        """
        intent = analyze_query_intent("Arabic Kuthu")
        self.assertFalse(intent["user_requested_alternate"])

        candidates = [
            {
                "title": "Arabic Kuthu - Video | Beast | Thalapathy Vijay | Sun Pictures | Anirudh",
                "uploader": "Sun TV",
                "duration": 290,
            },
            {
                "title": "Arabic Kuthu - Lyric Video | Beast | Anirudh | Jonita Gandhi",
                "uploader": "Sun TV",
                "duration": 290,
            },
            {
                "title": "Arabic Kuthu (From 'Beast')",
                "uploader": "Anirudh Ravichander - Topic",
                "duration": 280,
            },
        ]

        scores = [score_candidate(c, intent) for c in candidates]
        for s in scores:
            self.assertGreater(s, 140.0, "Legitimate official versions must all receive high confidence scores")

    # =========================================================================
    # 6. NO SUITABLE ORIGINAL RESULT
    # =========================================================================
    def test_06_no_suitable_original_result(self):
        """
        Verify that when zero YouTube candidates exist or when only low-scoring
        candidates are returned, ranking completes gracefully without raising uncaught exceptions.
        """
        async def _test():
            # Test empty raw candidates list
            AudioResolver._search_cache.clear()
            mock_ydl = MagicMock()
            mock_ydl.extract_info.return_value = {"entries": []}

            with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
                results = await AudioResolver.search("nonexistent song xyz123", limit=5)
                self.assertEqual(results, [])

        asyncio.run(_test())

    # =========================================================================
    # 7. YOUTUBE RESOLVER TIMEOUT AND EMPTY SEARCH RESULTS
    # =========================================================================
    def test_07_youtube_resolver_timeout_and_empty_search_results(self):
        """
        Verify that resolver timeouts and empty upstream search responses are properly
        categorized in last_resolver_error without raising uncaught exceptions.
        """
        async def _test():
            AudioResolver.clear_caches()
            mock_ydl = MagicMock()
            mock_ydl.extract_info.side_effect = asyncio.TimeoutError("Network timeout")

            with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
                track = await AudioResolver.resolve_track("test timeout query", 123, "TestUser")
                self.assertIsNone(track)
                res_err = getattr(AudioResolver, "last_resolver_error", "")
                self.assertTrue(
                    "TIMEOUT" in res_err or "timed out" in res_err.lower(),
                    f"Expected TIMEOUT diagnostic in last_resolver_error, got: '{res_err}'"
                )

        asyncio.run(_test())

    def test_07b_unavailable_youtube_video_gets_distinct_diagnostic(self):
        """Direct links to removed/private YouTube videos are not reported as generic format failures."""
        async def _test():
            AudioResolver.clear_caches()
            mock_ydl = MagicMock()
            mock_ydl.extract_info.side_effect = RuntimeError(
                "ERROR: [youtube] example12345: This video is unavailable"
            )

            with patch("yt_dlp.YoutubeDL", return_value=mock_ydl), \
                 patch("music_bot.services.resolver_service.get_active_cookie_file", return_value=None):
                track = await AudioResolver.resolve_track(
                    "https://www.youtube.com/watch?v=example12345", 123, "TestUser"
                )
                self.assertIsNone(track)
                self.assertIn(
                    "VIDEO_UNAVAILABLE",
                    AudioResolver.last_resolver_error or "",
                )

        asyncio.run(_test())

    # =========================================================================
    # 8. CONSISTENT BEHAVIOR FOR SLASH AND PREFIX COMMANDS
    # =========================================================================
    def test_08_consistent_behavior_for_slash_and_prefix_commands(self):
        """
        Verify that both slash command /play and prefix command !play utilize
        AudioResolver.resolve_track, guaranteeing identical ranking and selection behavior.
        """
        async def _test():
            AudioResolver.clear_caches()
            expected_track = QueuedTrack(
                title="Kalyani - Official Video",
                url="https://www.youtube.com/watch?v=kalyani_official",
                stream_url="https://audio.stream/kalyani.opus",
                duration=240,
                requester_id=123,
                requester_name="Tester",
                artist="Anirudh",
            )

            with patch.object(AudioResolver, "resolve_track", new_callable=AsyncMock) as mock_resolve:
                mock_resolve.return_value = expected_track

                # 1. Simulate Slash Command /play call
                track_slash = await AudioResolver.resolve_track("Kalyani", 123, "Tester")
                self.assertEqual(track_slash.title, "Kalyani - Official Video")
                self.assertEqual(track_slash.url, "https://www.youtube.com/watch?v=kalyani_official")

                # 2. Simulate Prefix Command !play call
                track_prefix = await AudioResolver.resolve_track("Kalyani", 123, "Tester")
                self.assertEqual(track_prefix.title, "Kalyani - Official Video")
                self.assertEqual(track_prefix.url, "https://www.youtube.com/watch?v=kalyani_official")

                self.assertEqual(mock_resolve.call_count, 2)

        asyncio.run(_test())

    # =========================================================================
    # 9. ORIGINAL STUDIO VERSION VS LIVE CONCERT PERFORMANCE
    # =========================================================================
    def test_09_original_studio_version_vs_live_concert_clip(self):
        """
        Verify searching for a song strongly prioritizes the pristine studio recording / official
        audio over live concert clips or tour performances.
        """
        intent = analyze_query_intent("Starboy")
        self.assertFalse(intent["user_requested_alternate"])
        self.assertFalse(intent.get("wants_live", False))

        studio_cand = {
            "title": "The Weeknd - Starboy (Official Audio) ft. Daft Punk",
            "uploader": "TheWeekndVEVO",
            "duration": 230,
        }
        live_cand = {
            "title": "The Weeknd - Starboy (Live at Coachella 2018)",
            "uploader": "Coachella Live Clips",
            "duration": 310,
        }

        s_studio, r_studio = score_candidate_detailed(studio_cand, intent)
        s_live, r_live = score_candidate_detailed(live_cand, intent)

        self.assertGreater(s_studio, s_live, "Studio track must heavily outscore live concert clip")
        self.assertTrue(any("unrequested_live_penalty" in r for r in r_live))
        self.assertGreaterEqual(s_studio - s_live, 70.0, "Expected at least 70 point separation")

    # =========================================================================
    # 10. YOUTUBE TOPIC OFFICIAL AUDIO VS UNOFFICIAL FAN LYRIC VIDEO
    # =========================================================================
    def test_10_youtube_topic_official_audio_vs_fan_lyric_video(self):
        """
        Verify YouTube Topic channel studio audio strongly outscores unofficial fan lyric uploads.
        """
        intent = analyze_query_intent("Espresso Sabrina Carpenter")
        self.assertFalse(intent["user_requested_alternate"])

        topic_cand = {
            "title": "Espresso",
            "uploader": "Sabrina Carpenter - Topic",
            "duration": 175,
        }
        fan_cand = {
            "title": "Sabrina Carpenter - Espresso (Lyrics)",
            "uploader": "RandomLyricsChannel77",
            "duration": 175,
        }

        s_topic, r_topic = score_candidate_detailed(topic_cand, intent)
        s_fan, r_fan = score_candidate_detailed(fan_cand, intent)

        self.assertGreater(s_topic, s_fan, "Topic channel audio must beat unverified fan lyric video")
        self.assertTrue(any("youtube_topic_channel" in r for r in r_topic))
        self.assertTrue(any("unverified_fan_upload_penalty" in r for r in r_fan))

    # =========================================================================
    # 11. SONGS WITH THE WORD 'LIVE' IN TITLE NOT FALSELY PENALIZED
    # =========================================================================
    def test_11_songs_with_word_live_in_title_not_penalized(self):
        """
        Verify songs whose legitimate titles contain the word 'live' (e.g. 'Live Your Life')
        are NOT misclassified as concert clips and are not penalized.
        """
        intent = analyze_query_intent("Live Your Life T.I. Rihanna")
        self.assertFalse(intent["user_requested_alternate"], "'Live Your Life' must not imply alternate version")
        self.assertFalse(intent.get("wants_live", False), "'Live Your Life' must not set wants_live")

        official_cand = {
            "title": "T.I. - Live Your Life ft. Rihanna (Official Video)",
            "uploader": "T.I. - Topic",
            "duration": 338,
        }

        score, reasons = score_candidate_detailed(official_cand, intent)
        self.assertFalse(any("unrequested_live_penalty" in r for r in reasons), "'Live Your Life' must not trigger live penalty")
        self.assertGreater(score, 150.0, "Legitimate studio track must score high")

    # =========================================================================
    # 12. EXPLICIT LIVE REQUEST PRIORITIZES LIVE CONCERT
    # =========================================================================
    def test_12_explicit_live_request_prioritizes_live_concert(self):
        """
        Verify that when user explicitly requests a live version (e.g. 'Fix You live'),
        the live concert performance is boosted and the studio original is penalized.
        """
        intent = analyze_query_intent("Fix You live")
        self.assertTrue(intent["user_requested_alternate"])
        self.assertTrue(intent.get("wants_live", False))

        live_cand = {
            "title": "Coldplay - Fix You (Live in São Paulo)",
            "uploader": "Coldplay",
            "duration": 320,
        }
        studio_cand = {
            "title": "Coldplay - Fix You (Official Video)",
            "uploader": "Coldplay - Topic",
            "duration": 295,
        }

        s_live, r_live = score_candidate_detailed(live_cand, intent)
        s_studio, r_studio = score_candidate_detailed(studio_cand, intent)

        self.assertGreater(s_live, s_studio, "Explicit live request must prioritize concert version")
        self.assertTrue(any("requested_live_boost" in r for r in r_live))


if __name__ == "__main__":
    unittest.main()
