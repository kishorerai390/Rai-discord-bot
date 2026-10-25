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
        DynamicPresenceService._mode = "dynamic"
        DynamicPresenceService._custom_status = "online"
        DynamicPresenceService._custom_activity_type = "listening"
        DynamicPresenceService._custom_activity_text = ""
        DynamicPresenceService._custom_idle_text = None
        DynamicPresenceService._signature_symbol = "vr_headset"

        self.bot = MagicMock()
        self.bot.is_ready.return_value = True
        self.bot.status = discord.Status.online
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
        self.assertTrue(sig.startswith("STATE:IDLE"))

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
        self.assertTrue(sig.startswith("STATE:IDLE"))

    def test_failed_or_stopped_playback_reports_idle(self):
        session = self.sm.get_session_sync(12345)
        session.state = PlaybackState.ERROR

        act, status, sig = DynamicPresenceService.resolve_target_activity(self.bot)
        self.assertEqual(act.name, DEFAULT_IDLE_ACTIVITY)
        self.assertTrue(sig.startswith("STATE:IDLE"))

    def test_recovery_state_takes_precedence(self):
        session = self.sm.get_session_sync(12345)
        session.state = PlaybackState.RECOVERING

        act, status, sig = DynamicPresenceService.resolve_target_activity(self.bot)
        self.assertEqual(act.name, DEFAULT_RECOVERY_ACTIVITY)
        self.assertTrue(sig.startswith("STATE:RECOVERING"))

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

    def test_manual_override_presence(self):
        import asyncio
        asyncio.run(DynamicPresenceService.update_state(
            self.bot,
            mode="manual",
            status="dnd",
            activity_type="playing",
            activity_text="Custom Game | /help",
        ))

        act, status, sig = DynamicPresenceService.resolve_target_activity(self.bot)
        self.assertEqual(act.name, "Custom Game | /help")
        self.assertEqual(act.type, discord.ActivityType.playing)
        self.assertEqual(status, discord.Status.dnd)
        self.assertTrue(sig.startswith("STATE:MANUAL:dnd:playing:Custom Game | /help"))

        # Reset back to dynamic
        asyncio.run(DynamicPresenceService.update_state(
            self.bot,
            mode="dynamic",
            status="online",
            activity_type="listening",
            activity_text="",
            idle_text="",
        ))
        state = DynamicPresenceService.get_state()
        self.assertEqual(state["mode"], "dynamic")
        self.assertEqual(state["status"], "online")

    def test_custom_idle_text_override(self):
        import asyncio
        asyncio.run(DynamicPresenceService.update_state(
            self.bot,
            mode="dynamic",
            idle_text="Special Community Jam",
        ))

        act, status, sig = DynamicPresenceService.resolve_target_activity(self.bot)
        self.assertEqual(act.name, "Special Community Jam")
        self.assertTrue(sig.startswith("STATE:IDLE"))

        # Cleanup
        asyncio.run(DynamicPresenceService.update_state(
            self.bot,
            idle_text="",
        ))

    def test_signature_symbol_selection_and_persistence(self):
        import asyncio
        # Test each of the 6 signature symbols
        valid_symbols = ["vr_headset", "music_note", "soundwave", "radio", "vinyl", "energy_core"]
        for sym in valid_symbols:
            res = asyncio.run(DynamicPresenceService.update_state(
                self.bot,
                signature_symbol=sym
            ))
            self.assertEqual(res["signature_symbol"], sym)
            state = DynamicPresenceService.get_state(self.bot)
            self.assertEqual(state["signature_symbol"], sym)

    def test_signature_symbol_allowlist_validation_rejects_invalid(self):
        import asyncio
        # Set to known valid first
        asyncio.run(DynamicPresenceService.update_state(self.bot, signature_symbol="music_note"))
        self.assertEqual(DynamicPresenceService._signature_symbol, "music_note")

        # Attempt to pass an invalid or malicious symbol
        asyncio.run(DynamicPresenceService.update_state(self.bot, signature_symbol="invalid_symbol_hacked"))
        # Must retain previous valid symbol and not accept the invalid one
        self.assertEqual(DynamicPresenceService._signature_symbol, "music_note")

    def test_reset_signature_symbol_restores_vr_headset_default(self):
        import asyncio
        # First set to energy_core
        asyncio.run(DynamicPresenceService.update_state(self.bot, signature_symbol="energy_core"))
        self.assertEqual(DynamicPresenceService._signature_symbol, "energy_core")

        # Now reset to default 'vr_headset'
        res = asyncio.run(DynamicPresenceService.update_state(self.bot, signature_symbol="vr_headset"))
        self.assertEqual(res["signature_symbol"], "vr_headset")
        self.assertEqual(DynamicPresenceService._signature_symbol, "vr_headset")

    def test_apply_each_supported_status_in_dynamic_and_manual(self):
        import asyncio
        for st in ["online", "idle", "dnd", "invisible"]:
            # Test in Dynamic mode
            asyncio.run(DynamicPresenceService.update_state(self.bot, mode="dynamic", status=st))
            act, status, sig = DynamicPresenceService.resolve_target_activity(self.bot)
            expected_status = {
                "online": discord.Status.online,
                "idle": discord.Status.idle,
                "dnd": discord.Status.dnd,
                "invisible": discord.Status.invisible,
            }[st]
            self.assertEqual(status, expected_status)
            self.assertTrue(sig.endswith(f":{st}"))

            # Test in Manual mode
            asyncio.run(DynamicPresenceService.update_state(self.bot, mode="manual", status=st, activity_text="Test"))
            act_m, status_m, sig_m = DynamicPresenceService.resolve_target_activity(self.bot)
            self.assertEqual(status_m, expected_status)
            self.assertIn(f":MANUAL:{st}:", sig_m)

    def test_invisible_status_retains_active_gateway_connection(self):
        import asyncio
        asyncio.run(DynamicPresenceService.update_state(self.bot, status="invisible"))
        state = DynamicPresenceService.get_state(self.bot)

        # Configured is invisible, but gateway is 100% active and connected
        self.assertEqual(state["configured_status"], "invisible")
        self.assertEqual(state["gateway_connected"], True)
        self.assertNotEqual(state["playback_state"], "unavailable")

    def test_five_independent_status_fields_reporting(self):
        import asyncio
        # Add an active music session with connected voice client
        session = self.sm.get_session_sync(999)
        track = QueuedTrack(url="u", title="Song", artist="Art", duration=120, requester_id=1, requester_name="U")
        session.current_track = track
        session.state = PlaybackState.PLAYING

        vc = MagicMock()
        vc.is_connected.return_value = True
        vc.is_playing.return_value = True
        vc.is_paused.return_value = False
        vc.channel.name = "General VC"
        session.voice_client = vc

        asyncio.run(DynamicPresenceService.update_state(self.bot, mode="dynamic", status="dnd"))
        state = DynamicPresenceService.get_state(self.bot)

        self.assertEqual(state["configured_status"], "dnd")
        self.assertEqual(state["gateway_connected"], True)
        self.assertEqual(state["discord_presence"], "online")
        self.assertEqual(state["voice_connected"], True)
        self.assertEqual(state["voice_channel"], "General VC")
        self.assertEqual(state["playback_state"], "playing")

    def test_stale_or_missing_bot_telemetry_reports_unknown(self):
        state = DynamicPresenceService.get_state(bot=None)
        self.assertEqual(state["gateway_connected"], False)
        self.assertEqual(state["discord_presence"], "unknown")
        self.assertEqual(state["playback_state"], "unavailable")

    def test_persistence_across_service_reloads(self):
        import asyncio
        asyncio.run(DynamicPresenceService.update_state(
            self.bot,
            mode="dynamic",
            status="idle",
            signature_symbol="vinyl",
            idle_text="Lossless Audio Studio"
        ))

        # Reset in-memory config and reload from disk
        DynamicPresenceService._config_loaded = False
        DynamicPresenceService.load_config()

        self.assertEqual(DynamicPresenceService._mode, "dynamic")
        self.assertEqual(DynamicPresenceService._custom_status, "idle")
        self.assertEqual(DynamicPresenceService._signature_symbol, "vinyl")
        self.assertEqual(DynamicPresenceService._custom_idle_text, "Lossless Audio Studio")


if __name__ == "__main__":
    unittest.main()
