import asyncio
import time
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from music_bot.services.resolver_service import AudioResolver, analyze_query_intent, score_candidate


class TestLivePlaybackResolution(unittest.IsolatedAsyncioTestCase):
    async def test_01_query_intent_and_candidate_scoring(self):
        # 1. Test Tamil language detection
        intent_tamil = analyze_query_intent("kalyani tamil")
        self.assertEqual(intent_tamil["detected_language"], "tamil")
        self.assertFalse(intent_tamil["wants_remix"])

        # 2. Test remix intent detection
        intent_remix = analyze_query_intent("faded alan walker remix")
        self.assertTrue(intent_remix["wants_remix"])

        # 3. Score comparison: unrequested remix vs original
        orig_cand = {"title": "Kalyani Vachen | Official Video", "uploader": "Sony Music South", "duration": 240}
        remix_cand = {"title": "Kalyani Vachen (DJ Remix)", "uploader": "Random DJ", "duration": 200}
        s_orig = score_candidate(orig_cand, intent_tamil)
        s_remix = score_candidate(remix_cand, intent_tamil)
        self.assertGreater(s_orig, s_remix, "Original track must score higher than unrequested remix")

        # 4. Score comparison when remix IS requested
        s_orig_for_remix = score_candidate(orig_cand, intent_remix)
        s_remix_for_remix = score_candidate(remix_cand, intent_remix)
        self.assertGreater(s_remix_for_remix, s_orig_for_remix, "Remix candidate must score higher when remix requested")

    async def test_02_resolve_kalyani_without_cookies(self):
        track = await AudioResolver.resolve_track("kalyani", 12345, "Tester")
        self.assertIsNotNone(track, f"Failed resolving 'kalyani': {AudioResolver.last_resolver_error}")
        self.assertTrue(bool(track.stream_url), "Stream URL must be populated")

    async def test_03_resolve_enna_sonna_hindi(self):
        track = await AudioResolver.resolve_track("enna sonna", 12345, "Tester")
        self.assertIsNotNone(track, f"Failed resolving 'enna sonna': {AudioResolver.last_resolver_error}")
        self.assertTrue(bool(track.stream_url), "Stream URL must be populated")

    async def test_04_resolve_tamil_query_kaappaan(self):
        track = await AudioResolver.resolve_track("Kaappaan Hey Amigo", 12345, "Tester")
        self.assertIsNotNone(track, f"Failed resolving 'Kaappaan Hey Amigo': {AudioResolver.last_resolver_error}")
        self.assertTrue(bool(track.stream_url), "Stream URL must be populated")

    async def test_05_no_result_query_diagnostics(self):
        AudioResolver.last_resolver_error = None
        no_track = await AudioResolver.resolve_track("zzzzzzzzzzzz129837192837192873192837129873", 12345, "Tester")
        self.assertIsNone(no_track)
        err = AudioResolver.last_resolver_error or ""
        self.assertTrue("[NO_RESULTS]" in err or "[TIMEOUT]" in err, f"Expected [NO_RESULTS] or [TIMEOUT], got: {err}")
        self.assertIn("Ref: MM-", err)
        self.assertNotIn("cookie", err.lower(), "Diagnostic must not claim cookies are required for empty search")


if __name__ == "__main__":
    unittest.main()
