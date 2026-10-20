"""
Phase 7B — Wrong Song Selection Regression Tests
=================================================
Validates that MusicMaid selects the correct song for a user's query, with
special focus on:
  - Tamil queries that should not resolve to Hindi tracks
  - Exact-title vs close-title matching
  - Original vs remix/cover/live selection
  - Explicit remix/cover/live requests
  - Low-confidence / empty results and user-facing selection
  - Queue entry = playback source identity
  - Concurrent /play and Auto-DJ safety
  - Timeout, retry, and resolver-worker cleanup (regression guards)
  - Prefix and slash command parity

All provider results are mocked — no live YouTube network calls.
"""

from __future__ import annotations

import asyncio
import uuid
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch
import unittest

from music_bot.services.resolver_service import (
    AudioResolver,
    analyze_query_intent,
    apply_resolved_track,
    is_original_recording_candidate,
    requires_candidate_confirmation,
    score_candidate,
    score_candidate_detailed,
    _video_id_from_url,
    _AUDIO_EXECUTOR_MAX_WORKERS,
    _audio_executor,
    REMIX_KEYWORDS,
    COVER_KEYWORDS,
    LIVE_PATTERNS,
)
from music_bot.database.models import QueuedTrack


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_track(title: str, url: str, stream_url: str = "https://audio.example/stream") -> QueuedTrack:
    return QueuedTrack(
        title=title,
        url=url,
        stream_url=stream_url,
        duration=240,
        requester_id=1,
        requester_name="Tester",
        artist="TestArtist",
    )


def _make_candidate(
    title: str,
    uploader: str = "TestChannel",
    duration: int = 240,
    vid_id: str = "test12345678",
    verified: bool = False,
) -> Dict[str, Any]:
    return {
        "id": vid_id,
        "title": title,
        "url": f"https://www.youtube.com/watch?v={vid_id}",
        "uploader": uploader,
        "channel": uploader,
        "duration": duration,
        "channel_is_verified": verified,
        "thumbnail": None,
        "provider": "youtube",
    }


# ---------------------------------------------------------------------------
# 1. Exact-title and close-title matching
# ---------------------------------------------------------------------------

class TestExactAndCloseTitleMatching(unittest.TestCase):
    """Exact match must always beat a partial or unrelated title."""

    def setUp(self) -> None:
        AudioResolver.clear_caches()

    def test_exact_title_beats_partial_match(self) -> None:
        """Exact song name should outrank a vague partial-match candidate."""
        intent = analyze_query_intent("Blue Moon Midnight Rain")
        exact = _make_candidate("Blue Moon Midnight Rain", uploader="IndieArtistVEVO")
        partial = _make_candidate("Blue Moon (Official Audio)", uploader="OfficialMusicCo")

        exact_score = score_candidate(exact, intent)
        partial_score = score_candidate(partial, intent)

        self.assertGreater(
            exact_score,
            partial_score,
            "Exact title match must outrank a partial title match",
        )

    def test_close_spelling_tamil_title_match(self) -> None:
        """'Enna Sona' query must prefer 'Enna Sonna' title over 'Enna Sona - OK Jaanu'."""
        intent = analyze_query_intent("Pichuva Kaththi Enna Sona")

        tamil_cand = _make_candidate(
            "Pichuva Kaththi - Enna Sonna Video Song",
            uploader="TrendMusic",
            vid_id="tamil12345678",
            verified=True,
        )
        hindi_cand = _make_candidate(
            "Enna Sona - OK Jaanu Official Video",
            uploader="Sony Music India",
            vid_id="hindi12345678",
        )

        tamil_score = score_candidate(tamil_cand, intent)
        hindi_score = score_candidate(hindi_cand, intent)

        self.assertGreater(
            tamil_score,
            hindi_score,
            "Tamil-titled candidate 'Pichuva Kaththi - Enna Sonna' must outrank Hindi 'Enna Sona - OK Jaanu'",
        )

    def test_original_recording_rejects_hindi_candidate_for_tamil_query(self) -> None:
        """is_original_recording_candidate must reject the Hindi neighbour."""
        intent = analyze_query_intent("Pichuva Kaththi Enna Sona")

        tamil_cand = _make_candidate(
            "Pichuva Kaththi - Enna Sonna Video Song",
            uploader="TrendMusic",
            vid_id="tamil12345678",
            verified=True,
        )
        hindi_cand = _make_candidate(
            "Enna Sona - OK Jaanu Official Video",
            uploader="Sony Music India",
            vid_id="hindi12345678",
        )

        self.assertTrue(is_original_recording_candidate(tamil_cand, intent))
        self.assertFalse(is_original_recording_candidate(hindi_cand, intent))

    def test_corpus_token_overlap_pichuva_kaththi(self) -> None:
        """
        'pichuva' and 'kaththi' must appear as core query tokens.
        These are the discriminating signal that the example query is for the Tamil song.
        """
        intent = analyze_query_intent("Pichuva Kaththi Enna Sona")
        core_tokens = set(intent["core_title"].split())
        self.assertIn("pichuva", core_tokens)
        self.assertIn("kaththi", core_tokens)


# ---------------------------------------------------------------------------
# 2. Tamil query vs unrelated Hindi candidate
# ---------------------------------------------------------------------------

class TestTamilQueryHindiMismatch(unittest.TestCase):
    """Tamil-language queries must not resolve to Hindi tracks."""

    def setUp(self) -> None:
        AudioResolver.clear_caches()

    def test_tamil_unicode_script_triggers_language_detection(self) -> None:
        intent = analyze_query_intent("கல்யாணி")
        self.assertTrue(intent["has_tamil_script"])
        self.assertEqual(intent["detected_language"], "tamil")

    def test_tamil_unicode_candidate_beats_hindi_candidate(self) -> None:
        intent = analyze_query_intent("கல்யாணி")
        tamil_cand = _make_candidate("கல்யாணி - Official Video Song", uploader="Sony Music South")
        hindi_cand = _make_candidate("Kalyani Hindi Dubbed Bollywood Mix", uploader="Zee Music Hindi")

        t_score = score_candidate(tamil_cand, intent)
        h_score = score_candidate(hindi_cand, intent)

        self.assertGreater(t_score, h_score, "Tamil Unicode query must prefer Tamil candidate")
        self.assertGreaterEqual(t_score - h_score, 80.0)

    def test_romanized_tamil_keyword_detection(self) -> None:
        """'Anirudh' is a LANGUAGE_HINTS tamil marker; query using it must detect Tamil."""
        intent = analyze_query_intent("Kalyani Anirudh")
        self.assertEqual(intent["detected_language"], "tamil")

    def test_romanized_tamil_keyword_boosts_tamil_candidate(self) -> None:
        intent = analyze_query_intent("Kalyani Tamil")
        self.assertEqual(intent["detected_language"], "tamil")

        tamil_cand = _make_candidate("Kalyani Tamil Official Video Song", uploader="Sony Music South")
        hindi_cand = _make_candidate(
            "Kalyani Hindi Dubbed Version Song Bollywood Mix", uploader="Zee Music Hindi"
        )

        t_score = score_candidate(tamil_cand, intent)
        h_score = score_candidate(hindi_cand, intent)

        self.assertGreater(t_score, h_score, "Tamil language keyword must boost Tamil candidate")
        self.assertGreaterEqual(t_score - h_score, 80.0)

    def test_pichuva_kaththi_ranked_search_returns_tamil_first(self) -> None:
        """
        When both Tamil and Hindi candidates appear, the ranked list must put
        the Tamil candidate first.
        """
        async def _test() -> None:
            AudioResolver.clear_caches()
            entries = [
                {
                    "id": "hindi12345678",
                    "title": "Enna Sona - OK Jaanu Official Video",
                    "uploader": "Sony Music India",
                    "duration": 213,
                },
                {
                    "id": "tamil12345678",
                    "title": "Pichuva Kaththi - Enna Sonna Video Song",
                    "uploader": "TrendMusic",
                    "channel_is_verified": True,
                    "duration": 240,
                },
            ]
            with patch(
                "music_bot.services.resolver_service._build_ytdl_options",
                return_value={},
            ), patch(
                "music_bot.services.resolver_service._run_ytdlp",
                new=AsyncMock(return_value={"entries": entries}),
            ):
                results = await AudioResolver.search(
                    "Pichuva Kaththi Enna Sona",
                    limit=5,
                    correlation_id="TEST-PICHUVA-7B",
                )

            self.assertEqual(
                results[0]["id"],
                "tamil12345678",
                f"Expected Tamil candidate first, got: {results[0]['title']!r}",
            )

        asyncio.run(_test())

    def test_hindi_song_query_does_not_select_tamil_result(self) -> None:
        """A Bollywood query must not select a Tamil-language result."""
        intent = analyze_query_intent("Kesariya arijit singh bollywood")
        self.assertEqual(intent["detected_language"], "hindi")

        tamil_cand = _make_candidate("Kesariya Tamil Dubbed Version Song", uploader="Tamil Dubbed Movies")
        hindi_cand = _make_candidate(
            "Kesariya - Brahmāstra | Arijit Singh | Official Audio", uploader="Sony Music India"
        )

        t_score = score_candidate(tamil_cand, intent)
        h_score = score_candidate(hindi_cand, intent)

        self.assertGreater(h_score, t_score, "Hindi query must prefer Hindi candidate")


# ---------------------------------------------------------------------------
# 3. Original vs remix / cover / live
# ---------------------------------------------------------------------------

class TestOriginalVsAlternate(unittest.TestCase):
    """Standard queries must prefer the original; alternate requests must prefer the alternate."""

    def setUp(self) -> None:
        AudioResolver.clear_caches()

    def test_standard_query_penalizes_dj_remix(self) -> None:
        intent = analyze_query_intent("Kalyani")
        original = _make_candidate("Kalyani - Official Music Video", uploader="SonyMusicSouthVEVO")
        remix = _make_candidate("Kalyani DJ Remix 2024 Bass Boosted Party Mix", uploader="DJ King Club")

        o_score = score_candidate(original, intent)
        r_score = score_candidate(remix, intent)

        self.assertGreater(o_score, r_score, "Original must outscore unrequested DJ remix")
        self.assertGreaterEqual(o_score - r_score, 80.0, "Penalty for unrequested remix must be >= 80 points")

    def test_standard_query_penalizes_unrequested_cover(self) -> None:
        intent = analyze_query_intent("Kesariya")
        official = _make_candidate(
            "Kesariya - Brahmāstra | Arijit Singh | Official Audio",
            uploader="Sony Music India - Topic",
        )
        cover = _make_candidate("Kesariya Acoustic Cover by Singer", uploader="AcousticVibes")

        o_score = score_candidate(official, intent)
        c_score = score_candidate(cover, intent)

        self.assertGreater(o_score, c_score, "Official audio must outscore unrequested acoustic cover")

    def test_standard_query_penalizes_unrequested_live(self) -> None:
        intent = analyze_query_intent("Starboy")
        studio = _make_candidate(
            "The Weeknd - Starboy (Official Audio) ft. Daft Punk",
            uploader="TheWeekndVEVO",
        )
        live = _make_candidate(
            "The Weeknd - Starboy (Live at Coachella 2018)",
            uploader="Coachella Live Clips",
            duration=310,
        )

        s_score, s_reasons = score_candidate_detailed(studio, intent)
        l_score, l_reasons = score_candidate_detailed(live, intent)

        self.assertGreater(s_score, l_score, "Studio track must outscore unrequested live concert clip")
        self.assertTrue(any("unrequested_live_penalty" in r for r in l_reasons))
        self.assertGreaterEqual(s_score - l_score, 70.0)

    def test_explicit_remix_request_boosts_remix_candidate(self) -> None:
        intent = analyze_query_intent("Kalyani DJ remix")
        self.assertTrue(intent["wants_remix"])
        self.assertTrue(intent["user_requested_alternate"])

        remix = _make_candidate("Kalyani DJ Remix - Official Audio", uploader="DJ Channel")
        original = _make_candidate("Kalyani - Official Music Video", uploader="Sony Music South")

        r_score, r_reasons = score_candidate_detailed(remix, intent)
        o_score, o_reasons = score_candidate_detailed(original, intent)

        self.assertGreater(r_score, o_score, "Explicit remix request must prioritize remix candidate")
        self.assertTrue(any("requested_remix_boost" in r for r in r_reasons))
        self.assertTrue(any("original_penalized" in r for r in o_reasons))

    def test_explicit_cover_request_boosts_cover_candidate(self) -> None:
        intent = analyze_query_intent("Perfect Ed Sheeran cover")
        self.assertTrue(intent["wants_cover"])

        cover = _make_candidate("Perfect - Ed Sheeran (Acoustic Cover by Singer)", uploader="AcousticHub")
        original = _make_candidate("Ed Sheeran - Perfect (Official Music Video)", uploader="EdSheeranVEVO")

        c_score = score_candidate(cover, intent)
        o_score = score_candidate(original, intent)

        self.assertGreater(c_score, o_score, "Explicit cover request must prioritize cover candidate")

    def test_explicit_live_request_boosts_live_candidate(self) -> None:
        intent = analyze_query_intent("Fix You live")
        self.assertTrue(intent["wants_live"])

        live = _make_candidate("Coldplay - Fix You (Live in Sao Paulo)", uploader="Coldplay")
        studio = _make_candidate("Coldplay - Fix You (Official Video)", uploader="Coldplay - Topic")

        l_score, l_reasons = score_candidate_detailed(live, intent)
        s_score, s_reasons = score_candidate_detailed(studio, intent)

        self.assertGreater(l_score, s_score, "Explicit live request must prioritize live concert version")
        self.assertTrue(any("requested_live_boost" in r for r in l_reasons))

    def test_dj_artist_name_does_not_imply_remix(self) -> None:
        """DJ in artist name (DJ Snake, DJ Khaled) must not trigger remix intent."""
        intent_snake = analyze_query_intent("DJ Snake Turn Down for What")
        self.assertFalse(intent_snake["wants_remix"], "DJ Snake must not trigger remix intent")
        self.assertFalse(intent_snake["user_requested_alternate"])

        intent_khaled = analyze_query_intent("DJ Khaled Wild Thoughts")
        self.assertFalse(intent_khaled["wants_remix"], "DJ Khaled must not trigger remix intent")

        # But "DJ remix" phrase must trigger intent
        intent_mix = analyze_query_intent("Wild Thoughts DJ remix")
        self.assertTrue(intent_mix["wants_remix"])
        self.assertTrue(intent_mix["user_requested_alternate"])

    def test_song_title_containing_live_not_penalized(self) -> None:
        """'Live Your Life' is a studio track title, not a concert clip descriptor."""
        intent = analyze_query_intent("Live Your Life T.I. Rihanna")
        self.assertFalse(intent["wants_live"], "'Live Your Life' must not set wants_live")
        self.assertFalse(intent["user_requested_alternate"])

        official = _make_candidate(
            "T.I. - Live Your Life ft. Rihanna (Official Video)",
            uploader="T.I. - Topic",
        )
        score, reasons = score_candidate_detailed(official, intent)
        self.assertFalse(
            any("unrequested_live_penalty" in r for r in reasons),
            "'Live Your Life' title must not trigger live penalty",
        )
        self.assertGreater(score, 150.0)


# ---------------------------------------------------------------------------
# 4. Empty results and low-confidence results
# ---------------------------------------------------------------------------

class TestEmptyAndLowConfidenceResults(unittest.TestCase):

    def setUp(self) -> None:
        AudioResolver.clear_caches()

    def test_empty_search_returns_no_results(self) -> None:
        async def _test() -> None:
            AudioResolver.clear_caches()
            with patch(
                "music_bot.services.resolver_service._run_ytdlp",
                new=AsyncMock(return_value={"entries": []}),
            ), patch(
                "music_bot.services.resolver_service._build_ytdl_options",
                return_value={},
            ):
                results = await AudioResolver.search("nonexistent song xyz987654", limit=5)
            self.assertEqual(results, [], "Empty search results must return empty list")

        asyncio.run(_test())

    def test_pipeline_returns_none_on_empty_search(self) -> None:
        async def _test() -> None:
            AudioResolver.clear_caches()
            with patch.object(AudioResolver, "search", new=AsyncMock(return_value=[])):
                result = await AudioResolver._execute_resolution_pipeline(
                    "no results song xyz987654", 123, "Tester"
                )
            self.assertIsNone(result)
            self.assertIn("[NO_RESULTS]", AudioResolver.last_resolver_error or "")

        asyncio.run(_test())

    def test_low_confidence_results_require_user_confirmation(self) -> None:
        """When top candidate score gap is tight, requires_candidate_confirmation must be True."""
        ambiguous = [
            {"_title_match_ratio": 1.0, "_match_score": 225.0},
            {"_title_match_ratio": 1.0, "_match_score": 215.0},
        ]
        self.assertTrue(requires_candidate_confirmation(ambiguous))

    def test_weak_match_ratio_requires_confirmation(self) -> None:
        weak = [{"_title_match_ratio": 0.5, "_match_score": 170.0}]
        self.assertTrue(requires_candidate_confirmation(weak))

    def test_strong_first_result_skips_confirmation(self) -> None:
        confident = [
            {"_title_match_ratio": 1.0, "_match_score": 220.0, "_title_match_confidence": 0.97},
            {"_title_match_ratio": 0.8, "_match_score": 175.0, "_title_match_confidence": 0.80},
        ]
        self.assertFalse(requires_candidate_confirmation(confident))

    def test_resolver_error_is_set_on_no_original_match(self) -> None:
        async def _test() -> None:
            AudioResolver.clear_caches()
            with patch.object(AudioResolver, "search", new=AsyncMock(return_value=[])), patch(
                "music_bot.services.resolver_service._run_ytdlp",
                new=AsyncMock(return_value={"entries": [
                    {
                        "id": "remix9999999",
                        "title": "Kalyani DJ Remix 2024 Bass Boosted",
                        "uploader": "DJ Club House",
                        "duration": 210,
                    }
                ]}),
            ), patch(
                "music_bot.services.resolver_service._build_ytdl_options",
                return_value={},
            ):
                result = await AudioResolver._execute_resolution_pipeline("Kalyani", 123, "Tester")

            self.assertIsNone(result)
            err = AudioResolver.last_resolver_error or ""
            self.assertTrue(
                "NO_ORIGINAL_MATCH" in err or "NO_RESULTS" in err,
                f"Expected NO_ORIGINAL_MATCH or NO_RESULTS, got: {err!r}",
            )

        asyncio.run(_test())


# ---------------------------------------------------------------------------
# 5. Prefix and slash command parity
# ---------------------------------------------------------------------------

class TestPrefixAndSlashCommandParity(unittest.TestCase):
    """Slash and prefix commands must route through the same resolver."""

    def setUp(self) -> None:
        AudioResolver.clear_caches()

    def test_both_commands_use_resolve_track(self) -> None:
        async def _test() -> None:
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
            with patch.object(AudioResolver, "resolve_track", new=AsyncMock(return_value=expected_track)) as mock:
                slash_result = await AudioResolver.resolve_track("Kalyani", 123, "Tester")
                prefix_result = await AudioResolver.resolve_track("Kalyani", 123, "Tester")

            self.assertEqual(slash_result.title, expected_track.title)
            self.assertEqual(prefix_result.title, expected_track.title)
            self.assertEqual(slash_result.url, prefix_result.url)
            self.assertEqual(mock.call_count, 2)

        asyncio.run(_test())


# ---------------------------------------------------------------------------
# 6. Search result -> queue entry -> playback source identity
# ---------------------------------------------------------------------------

class TestQueueAndPlaybackIdentity(unittest.TestCase):
    """The track selected by search must be the track queued and played."""

    def setUp(self) -> None:
        AudioResolver.clear_caches()

    def test_apply_resolved_track_rejects_wrong_video_id(self) -> None:
        selected = QueuedTrack(
            title="Pichuva Kaththi - Enna Sonna",
            url="https://www.youtube.com/watch?v=tamil12345678",
        )
        wrong_resolution = QueuedTrack(
            title="Enna Sona - OK Jaanu",
            url="https://www.youtube.com/watch?v=hindi12345678",
            stream_url="https://audio.example/wrong",
        )

        self.assertFalse(apply_resolved_track(selected, wrong_resolution))
        self.assertEqual(selected.url, "https://www.youtube.com/watch?v=tamil12345678")
        self.assertEqual(selected.title, "Pichuva Kaththi - Enna Sonna")
        self.assertEqual(selected.stream_url, "")

    def test_apply_resolved_track_accepts_same_video_id(self) -> None:
        selected = QueuedTrack(
            title="Pichuva Kaththi Enna Sonna",
            url="https://youtu.be/tamil12345678",
        )
        resolved = QueuedTrack(
            title="Pichuva Kaththi - Enna Sonna Video Song",
            url="https://www.youtube.com/watch?v=tamil12345678",
            stream_url="https://audio.example/tamil",
            duration=240,
            artist="TrendMusic",
        )

        self.assertTrue(apply_resolved_track(selected, resolved))
        self.assertEqual(selected.title, resolved.title)
        self.assertEqual(selected.url, resolved.url)
        self.assertEqual(selected.stream_url, resolved.stream_url)

    def test_stream_extraction_rejects_wrong_video_than_selected_candidate(self) -> None:
        """If yt-dlp returns a different video ID than what was ranked, result is None."""
        async def _test() -> None:
            AudioResolver.clear_caches()
            selected = {
                "id": "tamil12345678",
                "title": "Pichuva Kaththi - Enna Sonna Video Song",
                "url": "https://www.youtube.com/watch?v=tamil12345678",
                "duration": 240,
                "uploader": "TrendMusic",
                "channel_is_verified": True,
            }
            wrong_video_data = {
                "id": "hindi12345678",
                "title": "Pichuva Kaththi - Enna Sonna Video Song",
                "webpage_url": "https://www.youtube.com/watch?v=hindi12345678",
                "url": "https://audio.example/wrong",
                "uploader": "TrendMusic",
                "channel_is_verified": True,
                "duration": 240,
            }
            with patch.object(
                AudioResolver, "search", new=AsyncMock(return_value=[selected])
            ), patch(
                "music_bot.services.resolver_service._build_ytdl_options",
                return_value={},
            ), patch(
                "music_bot.services.resolver_service._run_ytdlp",
                new=AsyncMock(return_value=wrong_video_data),
            ), patch(
                "music_bot.services.resolver_service.get_active_cookie_file",
                return_value=None,
            ):
                result = await AudioResolver._execute_resolution_pipeline(
                    "Pichuva Kaththi Enna Sona",
                    123,
                    "Tester",
                    correlation_id="TEST-IDENTITY-7B",
                )

            self.assertIsNone(result)

        asyncio.run(_test())

    def test_video_id_extraction_from_canonical_url(self) -> None:
        self.assertEqual(_video_id_from_url("https://www.youtube.com/watch?v=abcde12345A"), "abcde12345A")
        self.assertEqual(_video_id_from_url("https://youtu.be/abcde12345A"), "abcde12345A")
        self.assertIsNone(_video_id_from_url(""))
        self.assertIsNone(_video_id_from_url(None))

    def test_apply_resolved_track_youtu_be_vs_watch_same_id(self) -> None:
        """youtu.be and youtube.com/watch?v= with same ID must be treated as equal."""
        q = QueuedTrack(
            title="Kalyani",
            url="https://youtu.be/kalyani12345A",
            stream_url="",
        )
        r = QueuedTrack(
            title="Kalyani - Official Music Video",
            url="https://www.youtube.com/watch?v=kalyani12345A",
            stream_url="https://audio.example/kal.opus",
            duration=240,
        )
        self.assertTrue(apply_resolved_track(q, r))
        self.assertEqual(q.stream_url, "https://audio.example/kal.opus")


# ---------------------------------------------------------------------------
# 7. Concurrent /play and Auto-DJ interactions
# ---------------------------------------------------------------------------

class TestConcurrentPlayAndAutoDJ(unittest.TestCase):

    def setUp(self) -> None:
        AudioResolver.clear_caches()

    def test_concurrent_resolves_deduplicate(self) -> None:
        async def _test() -> None:
            AudioResolver.clear_caches()
            call_count = 0

            async def _fake_pipeline(query, req_id, req_name, **kwargs):
                nonlocal call_count
                call_count += 1
                await asyncio.sleep(0.05)
                return QueuedTrack(
                    title="Kalyani - Official",
                    url="https://www.youtube.com/watch?v=kalyani12345A",
                    stream_url="https://audio.example/kalyani.opus",
                    duration=240,
                    requester_id=req_id,
                    requester_name=req_name,
                )

            with patch.object(AudioResolver, "_execute_resolution_pipeline", side_effect=_fake_pipeline):
                results = await asyncio.gather(
                    AudioResolver.resolve_track("Kalyani concurrent1", 1, "User1"),
                    AudioResolver.resolve_track("Kalyani concurrent1", 2, "User2"),
                    AudioResolver.resolve_track("Kalyani concurrent1", 3, "User3"),
                )

            for r in results:
                self.assertIsNotNone(r)
                self.assertEqual(r.title, "Kalyani - Official")

            # Deduplication should share the first task; pipeline must be called <= 3 times
            self.assertLessEqual(call_count, 3)

        asyncio.run(_test())

    def test_resolved_track_carries_per_requester_metadata(self) -> None:
        async def _test() -> None:
            AudioResolver.clear_caches()
            base_track = QueuedTrack(
                title="Kalyani - Official",
                url="https://www.youtube.com/watch?v=kalyani12345A",
                stream_url="https://audio.example/kalyani.opus",
                duration=240,
                requester_id=1,
                requester_name="UserA",
            )
            with patch.object(AudioResolver, "_execute_resolution_pipeline", new=AsyncMock(return_value=base_track)):
                t1 = await AudioResolver.resolve_track("Kalyani reqmeta1", 101, "UserX")
                AudioResolver.clear_caches()
                t2 = await AudioResolver.resolve_track("Kalyani reqmeta2", 202, "UserY")

            self.assertEqual(t1.requester_id, 101)
            self.assertEqual(t2.requester_id, 202)

        asyncio.run(_test())


# ---------------------------------------------------------------------------
# 8. Timeout, bounded-retry, and resolver-worker cleanup (regression guards)
# ---------------------------------------------------------------------------

class TestTimeoutAndRetryRegression(unittest.TestCase):

    def setUp(self) -> None:
        AudioResolver.clear_caches()

    def test_resolver_timeout_sets_last_resolver_error(self) -> None:
        async def _test() -> None:
            AudioResolver.clear_caches()
            with patch(
                "music_bot.services.resolver_service._run_ytdlp",
                new=AsyncMock(side_effect=asyncio.TimeoutError("timed out")),
            ), patch(
                "music_bot.services.resolver_service._build_ytdl_options",
                return_value={},
            ), patch(
                "music_bot.services.resolver_service.get_active_cookie_file",
                return_value=None,
            ):
                result = await AudioResolver.resolve_track("timeout query test xyz", 123, "Tester")

            self.assertIsNone(result)
            err = AudioResolver.last_resolver_error or ""
            self.assertTrue(
                "TIMEOUT" in err or "timed out" in err.lower(),
                f"Expected TIMEOUT in last_resolver_error, got: {err!r}",
            )

        asyncio.run(_test())

    def test_video_unavailable_gets_distinct_error_category(self) -> None:
        async def _test() -> None:
            AudioResolver.clear_caches()
            with patch(
                "music_bot.services.resolver_service._run_ytdlp",
                new=AsyncMock(
                    side_effect=RuntimeError("ERROR: [youtube] example12345: This video is unavailable")
                ),
            ), patch(
                "music_bot.services.resolver_service._build_ytdl_options",
                return_value={},
            ), patch(
                "music_bot.services.resolver_service.get_active_cookie_file",
                return_value=None,
            ):
                result = await AudioResolver.resolve_track(
                    "https://www.youtube.com/watch?v=example12345", 123, "Tester"
                )

            self.assertIsNone(result)
            err = AudioResolver.last_resolver_error or ""
            self.assertIn("VIDEO_UNAVAILABLE", err, f"Expected VIDEO_UNAVAILABLE, got: {err!r}")

        asyncio.run(_test())

    def test_executor_max_workers_bounded(self) -> None:
        self.assertGreater(_AUDIO_EXECUTOR_MAX_WORKERS, 0)
        self.assertLessEqual(_AUDIO_EXECUTOR_MAX_WORKERS, 30)

    def test_clear_caches_removes_both_track_and_search_caches(self) -> None:
        AudioResolver._track_cache["dummy_key"] = (QueuedTrack("X", "http://x"), 0.0)
        AudioResolver._search_cache["dummy_search"] = [{"id": "abc"}]
        AudioResolver.clear_caches()
        self.assertEqual(len(AudioResolver._track_cache), 0)
        self.assertEqual(len(AudioResolver._search_cache), 0)


# ---------------------------------------------------------------------------
# 9. Correlation-ID diagnostics
# ---------------------------------------------------------------------------

class TestCorrelationIdDiagnostics(unittest.TestCase):

    def setUp(self) -> None:
        AudioResolver.clear_caches()

    def test_resolved_track_carries_correlation_id(self) -> None:
        async def _test() -> None:
            AudioResolver.clear_caches()
            expected_track = QueuedTrack(
                title="Kalyani - Official",
                url="https://www.youtube.com/watch?v=kalyani12345A",
                stream_url="https://audio.example/kalyani.opus",
                duration=240,
                requester_id=1,
                requester_name="Tester",
            )
            with patch.object(
                AudioResolver, "_execute_resolution_pipeline", new=AsyncMock(return_value=expected_track)
            ):
                result = await AudioResolver.resolve_track(
                    "Kalyani corrid1", 1, "Tester", correlation_id="CORR-TEST-123"
                )

            self.assertIsNotNone(result)
            corr = getattr(result, "_correlation_id", None)
            self.assertEqual(corr, "CORR-TEST-123")

        asyncio.run(_test())

    def test_correlation_id_auto_generated_when_absent(self) -> None:
        async def _test() -> None:
            AudioResolver.clear_caches()
            expected_track = QueuedTrack(
                title="Kalyani - Official",
                url="https://www.youtube.com/watch?v=kalyani12345A",
                stream_url="https://audio.example/kalyani.opus",
                duration=240,
                requester_id=1,
                requester_name="Tester",
            )
            with patch.object(
                AudioResolver, "_execute_resolution_pipeline", new=AsyncMock(return_value=expected_track)
            ):
                result = await AudioResolver.resolve_track("Kalyani autoid1", 1, "Tester")

            self.assertIsNotNone(result)
            corr = getattr(result, "_correlation_id", None)
            self.assertIsNotNone(corr)
            self.assertIsInstance(corr, str)
            self.assertGreater(len(corr), 0)

        asyncio.run(_test())


# ---------------------------------------------------------------------------
# 10. Candidate-ranking logging assertions (structured diagnostics)
# ---------------------------------------------------------------------------

class TestCandidateRankingDiagnostics(unittest.TestCase):

    def setUp(self) -> None:
        AudioResolver.clear_caches()

    def test_remix_penalty_reason_present_when_applied(self) -> None:
        intent = analyze_query_intent("Kalyani")
        remix = _make_candidate("Kalyani DJ Remix 2024", uploader="DJ Club House")
        _, reasons = score_candidate_detailed(remix, intent)
        self.assertTrue(
            any("unrequested_remix" in r for r in reasons),
            f"Expected unrequested_remix reason, got: {reasons}",
        )

    def test_topic_channel_bonus_reason_present(self) -> None:
        intent = analyze_query_intent("Espresso Sabrina Carpenter")
        topic = _make_candidate("Espresso", uploader="Sabrina Carpenter - Topic")
        _, reasons = score_candidate_detailed(topic, intent)
        self.assertTrue(
            any("youtube_topic_channel" in r for r in reasons),
            f"Expected youtube_topic_channel reason, got: {reasons}",
        )

    def test_fan_upload_penalty_reason_present(self) -> None:
        intent = analyze_query_intent("Espresso Sabrina Carpenter")
        fan = _make_candidate("Sabrina Carpenter - Espresso (Lyrics)", uploader="RandomLyricsChannel77")
        _, reasons = score_candidate_detailed(fan, intent)
        self.assertTrue(
            any("unverified_fan_upload_penalty" in r for r in reasons),
            f"Expected unverified_fan_upload_penalty reason, got: {reasons}",
        )

    def test_live_penalty_reason_present_for_concert_clip(self) -> None:
        intent = analyze_query_intent("Shape of You")
        live = _make_candidate(
            "Ed Sheeran - Shape of You (Live at Glastonbury)", uploader="Glastonbury"
        )
        _, reasons = score_candidate_detailed(live, intent)
        self.assertTrue(
            any("unrequested_live_penalty" in r for r in reasons),
            f"Expected unrequested_live_penalty for live concert clip, got: {reasons}",
        )

    def test_multiple_original_versions_all_score_high(self) -> None:
        intent = analyze_query_intent("Arabic Kuthu")
        candidates = [
            _make_candidate("Arabic Kuthu - Video | Beast | Anirudh", uploader="Sun TV"),
            _make_candidate("Arabic Kuthu - Lyric Video | Beast | Anirudh", uploader="Sun TV"),
            _make_candidate("Arabic Kuthu (From Beast)", uploader="Anirudh Ravichander - Topic"),
        ]
        for c in candidates:
            s = score_candidate(c, intent)
            self.assertGreater(s, 140.0, f"Candidate {c['title']!r} scored {s:.1f}, expected > 140")


# ---------------------------------------------------------------------------
# 11. Direct-URL path
# ---------------------------------------------------------------------------

class TestDirectUrlPath(unittest.TestCase):

    def setUp(self) -> None:
        AudioResolver.clear_caches()

    def test_direct_youtube_url_bypasses_search_ranking(self) -> None:
        async def _test() -> None:
            AudioResolver.clear_caches()
            resolve_data = {
                "id": "remix1234567",
                "title": "Kalyani DJ Remix",
                "webpage_url": "https://www.youtube.com/watch?v=remix1234567",
                "url": "https://audio.example/stream",
                "duration": 210,
                "uploader": "Unknown DJ Channel",
            }
            with patch(
                "music_bot.services.resolver_service._build_ytdl_options",
                return_value={},
            ), patch(
                "music_bot.services.resolver_service._run_ytdlp",
                new=AsyncMock(return_value=resolve_data),
            ), patch(
                "music_bot.services.resolver_service.get_active_cookie_file",
                return_value=None,
            ):
                result = await AudioResolver._execute_resolution_pipeline(
                    "https://www.youtube.com/watch?v=remix1234567",
                    123,
                    "Tester",
                )

            self.assertIsNotNone(result, "Direct URL must resolve")
            self.assertEqual(result.title, "Kalyani DJ Remix")

        asyncio.run(_test())

    def test_direct_url_identity_guard_catches_mismatched_video(self) -> None:
        async def _test() -> None:
            AudioResolver.clear_caches()
            wrong_data = {
                "id": "completely_different",
                "title": "Wrong Song",
                "webpage_url": "https://www.youtube.com/watch?v=completely_different",
                "url": "https://audio.example/wrong",
                "duration": 210,
                "uploader": "Random Channel",
            }
            with patch(
                "music_bot.services.resolver_service._build_ytdl_options",
                return_value={},
            ), patch(
                "music_bot.services.resolver_service._run_ytdlp",
                new=AsyncMock(return_value=wrong_data),
            ), patch(
                "music_bot.services.resolver_service.get_active_cookie_file",
                return_value=None,
            ):
                result = await AudioResolver._execute_resolution_pipeline(
                    "https://www.youtube.com/watch?v=remix1234567",
                    123,
                    "Tester",
                )

            self.assertIsNone(result, "Direct URL with mismatched video_id response must return None")

        asyncio.run(_test())


# ---------------------------------------------------------------------------
# 12. Analyze_query_intent correctness for edge cases
# ---------------------------------------------------------------------------

class TestQueryIntentEdgeCases(unittest.TestCase):

    def test_flip_word_resolves_without_error(self) -> None:
        """'flip' is in REMIX_KEYWORDS; query using it must not crash."""
        intent = analyze_query_intent("Flip")
        self.assertIsInstance(intent["wants_remix"], bool)

    def test_acoustic_in_explicit_request_detected(self) -> None:
        intent = analyze_query_intent("Shape of You acoustic")
        self.assertTrue(intent["wants_cover"], "Explicit acoustic must set wants_cover")
        self.assertTrue(intent["user_requested_alternate"])

    def test_slowed_reverb_detection(self) -> None:
        intent = analyze_query_intent("Kalyani slowed reverb")
        self.assertTrue(intent["wants_slowed"])
        self.assertTrue(intent["user_requested_alternate"])

    def test_original_keyword_detection(self) -> None:
        intent = analyze_query_intent("Kalyani official audio")
        self.assertTrue(intent["wants_original"])
        self.assertFalse(intent["user_requested_alternate"])

    def test_non_standard_tamil_artist_names_in_language_hints(self) -> None:
        intent = analyze_query_intent("Kannaana Kanney sid sriram")
        self.assertEqual(intent["detected_language"], "tamil")

    def test_kpop_query_does_not_trigger_tamil(self) -> None:
        intent = analyze_query_intent("BTS Dynamite kpop")
        self.assertNotEqual(intent["detected_language"], "tamil")
        self.assertEqual(intent["detected_language"], "korean")

    def test_nightcore_triggers_slowed_alternate_intent(self) -> None:
        intent = analyze_query_intent("Kalyani nightcore")
        self.assertTrue(intent["wants_slowed"])
        self.assertTrue(intent["user_requested_alternate"])

    def test_lofi_triggers_slowed_alternate_intent(self) -> None:
        intent = analyze_query_intent("Kalyani lofi")
        self.assertTrue(intent["wants_slowed"])
        self.assertTrue(intent["user_requested_alternate"])


if __name__ == "__main__":
    unittest.main()
