"""Regression tests for Rem's playback-driven mood state machine."""
import unittest
from types import SimpleNamespace

from music_bot.services.rem_mood_service import RemMoodService


class TestRemMoodService(unittest.TestCase):
    def setUp(self):
        self.session = SimpleNamespace()

    def test_track_start_and_completion_are_happy(self):
        self.assertEqual(RemMoodService.on_track_started(self.session)["mood"], "happy")
        result = RemMoodService.on_track_completed(self.session)
        self.assertEqual(result["mood"], "happy")
        self.assertEqual(result["completed_count"], 1)

    def test_same_track_requires_three_skips(self):
        track = SimpleNamespace(url="https://example.test/song", title="Song")
        self.assertEqual(RemMoodService.on_track_skipped(self.session, track)["mood"], "balanced")
        self.assertEqual(RemMoodService.on_track_skipped(self.session, track)["mood"], "balanced")
        result = RemMoodService.on_track_skipped(self.session, track)
        self.assertEqual(result["mood"], "annoyed")
        self.assertEqual(result["reason"], "same_track_skipped_three_times")

    def test_different_tracks_do_not_share_skip_streak(self):
        one = SimpleNamespace(url="song-1")
        two = SimpleNamespace(url="song-2")
        for _ in range(2):
            RemMoodService.on_track_skipped(self.session, one)
            RemMoodService.on_track_skipped(self.session, two)
        self.assertEqual(RemMoodService.get_status(self.session)["mood"], "balanced")

    def test_queue_empty_is_lonely(self):
        self.assertEqual(RemMoodService.on_queue_empty(self.session)["mood"], "lonely")

    def test_hyper_after_each_hundred_completed_tracks(self):
        self.session._rem_completed_count = 99
        result = RemMoodService.on_track_completed(self.session)
        self.assertEqual(result["mood"], "hyper")
        self.assertEqual(result["completed_count"], 100)

    def test_status_read_does_not_change_session_playback(self):
        self.session.state = "PLAYING"
        status = RemMoodService.get_status(self.session)
        self.assertEqual(status["mood"], "balanced")
        self.assertEqual(self.session.state, "PLAYING")


if __name__ == "__main__":
    unittest.main()
