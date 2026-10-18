import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import discord
from music_bot.services.presence_service import (
    DynamicPresenceService,
    DEFAULT_IDLE_ACTIVITY,
    DEFAULT_RECOVERY_ACTIVITY,
    MAX_ACTIVITY_LEN,
)
from music_bot.services.session_service import GuildMusicSession, PlaybackState, SessionManager
from music_bot.database.models import QueuedTrack


class TestDynamicPresenceService(unittest.TestCase):
    def setUp(self):
        # Reset SessionManager singleton sessions
        self.sm = SessionManager.get_instance()
        self.sm._sessions.clear()
        DynamicPresenceService._last_signature = None
        DynamicPresenceService._last_update_time = 0.0

        self.bot = MagicMock()
        self.bot.is_ready.return_value = True
        self.bot.change_presence = AsyncMock()

    def test_sanitize_track_metadata(self):
        # Basic title and artist
        res = DynamicPresenceService.sanitize_track_metadata("Stay", "The Kid LAROI, Justin Bieber")
        self.assertEqual(res, "Stay • The Kid LAROI, Justin Bieber")

        # Strip full URLs
        res_url = DynamicPresenceService.sanitize_track_metadata("https://www.youtube.com/watch?v=123 Song Name", None)
        self.assertEqual(res_url, "Song Name")

        # Unknown artist handled cleanly
        res_unknown = DynamicPresenceService.sanitize_track_metadata("My Cool Song", "unknown")
        self.assertEqual(res_unknown, "My Cool Song")

        # Long title truncated safely to <= MAX_ACTIVITY_LEN
        long_title = "A" * 200
        res_long = DynamicPresenceService.sanitize_track_metadata(long_title, "Artist")
        self.assertLessEqual(len(res_long), MAX_ACTIVITY_LEN)
        self.assertTrue(res_long.endswith("..."))

    def test_idle_presence_when_no_sessions(self):
        act, status, sig = DynamicPresenceService.resolve_target_activity(self.bot)
        self.assertEqual(act.name, DEFAULT_IDLE_ACTIVITY)
        self.assertEqual(act.type, discord.ActivityType.listening)
        self.assertEqual(status, discord.Status.online)
        self.assertEqual(sig, "STATE:IDLE")

    def test_playing_activity_with_correct_title_and_artist(self):
        session = self.sm.get_session_sync(12345)
        track = QueuedTrack(
            url="https://youtube.com/watch?v=123",
            title="Blinding Lights",
            artist="The Weeknd",
            duration=200,
            requester_id=1,
            requester_name="User",
        )
        session.current_track = track
        session.state = PlaybackState.PLAYING

        # Mock active voice client
        vc = MagicMock()
        vc.is_playing.return_value = True
        vc.is_paused.return_value = False
        vc.channel = MagicMock()
        session.voice_client = vc

        act, status, sig = DynamicPresenceService.resolve_target_activity(self.bot)
        self.assertEqual(act.name, "Blinding Lights • The Weeknd")
        self.assertEqual(act.type, discord.ActivityType.listening)
        self.assertTrue(sig.startswith("STATE:PLAYING"))

    def test_paused_playback_reports_idle_not_playing(self):
        session = self.sm.get_session_sync(12345)
        track = QueuedTrack(
            url="https://youtube.com/watch?v=123",
            title="Levitating",
            artist="Dua Lipa",
            duration=200,
            requester_id=1,
            requester_name="User",
        )
        session.current_track = track
        session.state = PlaybackState.PAUSED

        vc = MagicMock()
        vc.is_playing.return_value = False
        vc.is_paused.return_value = True
        vc.channel = MagicMock()
        session.voice_client = vc

        act, status, sig = DynamicPresenceService.resolve_target_activity(self.bot)
        self.assertEqual(act.name, DEFAULT_IDLE_ACTIVITY)
        self.assertEqual(sig, "STATE:IDLE")

    def test_failed_or_stopped_playback_reports_idle(self):
        session = self.sm.get_session_sync(12345)
        session.state = PlaybackState.ERROR

        act, status, sig = DynamicPresenceService.resolve_target_activity(self.bot)
        self.assertEqual(act.name, DEFAULT_IDLE_ACTIVITY)
        self.assertEqual(sig, "STATE:IDLE")

    def test_recovery_state_takes_precedence(self):
        session = self.sm.get_session_sync(12345)
        session.state = PlaybackState.RECOVERING

        act, status, sig = DynamicPresenceService.resolve_target_activity(self.bot)
        self.assertEqual(act.name, DEFAULT_RECOVERY_ACTIVITY)
        self.assertEqual(sig, "STATE:RECOVERING")

    def test_sync_presence_rate_limiting_and_transitions(self):
        import asyncio

        # Initial idle sync
        asyncio.run(DynamicPresenceService.sync_presence(self.bot, force=True))
        self.bot.change_presence.assert_called_once()
        self.bot.change_presence.reset_mock()

        # Immediate redundant call with same state should be skipped
        asyncio.run(DynamicPresenceService.sync_presence(self.bot, force=False))
        self.bot.change_presence.assert_not_called()

        # State transition to playing should bypass interval throttle
        session = self.sm.get_session_sync(12345)
        track = QueuedTrack(url="url", title="Song A", artist="Band B", duration=100, requester_id=1, requester_name="U")
        session.current_track = track
        session.state = PlaybackState.PLAYING
        vc = MagicMock()
        vc.is_playing.return_value = True
        vc.is_paused.return_value = False
        vc.channel = MagicMock()
        session.voice_client = vc

        asyncio.run(DynamicPresenceService.sync_presence(self.bot, force=False))
        self.bot.change_presence.assert_called_once()


if __name__ == "__main__":
    unittest.main()
