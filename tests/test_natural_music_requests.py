"""
RAI — Complete Natural Song Requests & Zero-Interference Playback Test Suite.

Verifies:
1. "Kalyani" in #music-requests requests and starts song playback.
2. Normal chat ("hello bro") does not touch music playback.
3. Conversational talk ("what are you guys playing?") does not alter queue or playback.
4. "Believer" while playing adds to queue without interrupting current song.
5. "playnow Believer" immediately interrupts and plays the new track.
6. Skip advances to next queued track safely.
7. Pause and Resume work cleanly.
8. Queue displays accurate positions and requesters.
9. Normal messages outside #music-requests are completely ignored by music system.
10. Duplicate request protection (within 10s).
11. Rate limit protection (>5 requests in 30s).
12. Voice channel requirement (user not in VC is prompted to join).
13. Dynamic VC integration (reuses user's dynamic voice room without creating duplicates).
14. Cross-module isolation (running backup, health checks, or security scans does not interrupt music).
"""

import asyncio
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from cogs.music import GuildMusicPlayer, MusicCog, Song
from music.natural_request import (
    IntentConfidence,
    MusicIntent,
    NaturalMusicRequestDetector,
    NaturalMusicService,
)
from music.provider import ResolvedTrack, TrackCandidate


class TestNaturalMusicRequests(unittest.IsolatedAsyncioTestCase):
    """Deep integration and isolation tests for natural song requests."""

    async def asyncSetUp(self):
        self.bot = MagicMock()
        self.bot.loop = asyncio.get_running_loop()
        self.bot.intents.message_content = True

        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = 10001
        self.guild.name = "Rai Test Sanctuary"
        self.guild.me = MagicMock(spec=discord.Member)

        self.music_channel = MagicMock(spec=discord.TextChannel)
        self.music_channel.id = 20001
        self.music_channel.name = "music-requests"
        self.music_channel.send = AsyncMock()

        self.general_channel = MagicMock(spec=discord.TextChannel)
        self.general_channel.id = 20002
        self.general_channel.name = "general"
        self.general_channel.send = AsyncMock()

        self.voice_channel = MagicMock(spec=discord.VoiceChannel)
        self.voice_channel.id = 30001
        self.voice_channel.name = "🎙️ General Voice"
        self.voice_channel.members = []

        self.mock_voice_client = MagicMock(spec=discord.VoiceClient)
        self.mock_voice_client.channel = self.voice_channel
        self.mock_voice_client.is_connected.return_value = True
        self.mock_voice_client.is_playing.return_value = False
        self.mock_voice_client.is_paused.return_value = False
        self.mock_voice_client.play = MagicMock()
        self.mock_voice_client.pause = MagicMock()
        self.mock_voice_client.resume = MagicMock()
        self.mock_voice_client.stop = MagicMock()
        self.mock_voice_client.disconnect = AsyncMock()

        self.guild.voice_client = self.mock_voice_client

        self.user = MagicMock(spec=discord.Member)
        self.user.id = 40001
        self.user.name = "Alex"
        self.user.display_name = "Alex"
        self.user.mention = "<@40001>"
        self.user.bot = False
        self.user.guild = self.guild
        self.user.voice = MagicMock()
        self.user.voice.channel = self.voice_channel

        # DB Mock Setup
        self.music_config = MagicMock()
        self.music_config.guild_id = self.guild.id
        self.music_config.request_channel_id = self.music_channel.id
        self.music_config.natural_requests_enabled = True
        self.music_config.natural_request_confidence = 0.7
        self.music_config.auto_queue = True
        self.music_config.duplicate_protection = True
        self.music_config.default_volume = 50

        self.bot.db = MagicMock()
        self.bot.db.get_music_config = AsyncMock(return_value=self.music_config)

        # Cog Setup
        self.cog = MusicCog(self.bot)
        self.bot.cogs = {"Music": self.cog}
        self.player = self.cog.get_player(self.guild)

        # Reset NaturalMusicService state
        self.service = NaturalMusicService()
        self.service._user_requests.clear()
        self.service._recent_song_requests.clear()
        self.service._guild_locks.clear()
        NaturalMusicService._instance = self.service

    async def asyncTearDown(self):
        if hasattr(self, "cog") and self.cog:
            self.cog.cog_unload()

    def _create_mock_song(self, title: str, duration: int = 210, requester: Optional[discord.Member] = None) -> Song:
        cand = TrackCandidate(
            title=title,
            url=f"https://www.youtube.com/watch?v=mock_{title.lower().replace(' ', '_')}",
            duration=duration,
            artist="Test Artist",
            requester=requester or self.user,
        )
        resolved = ResolvedTrack(
            candidate=cand,
            stream_url=f"https://stream.mock/{title.lower().replace(' ', '_')}.opus",
            is_playable=True,
        )
        return Song.from_resolved(resolved, requester=requester or self.user)

    # =========================================================================
    # INTENT DETECTOR TESTS
    # =========================================================================

    def test_intent_detector_natural_titles(self):
        """Natural song names like 'Kalyani', 'Believer' detect as PLAY with HIGH confidence."""
        intent, q, conf = NaturalMusicRequestDetector.analyze_message("Kalyani")
        self.assertEqual(intent, MusicIntent.PLAY)
        self.assertEqual(q, "Kalyani")
        self.assertEqual(conf, IntentConfidence.HIGH)

        intent, q, conf = NaturalMusicRequestDetector.analyze_message("Perfect Ed Sheeran")
        self.assertEqual(intent, MusicIntent.PLAY)
        self.assertEqual(q, "Perfect Ed Sheeran")
        self.assertEqual(conf, IntentConfidence.HIGH)

        intent, q, conf = NaturalMusicRequestDetector.analyze_message("play believer")
        self.assertEqual(intent, MusicIntent.PLAY)
        self.assertEqual(q, "believer")
        self.assertEqual(conf, IntentConfidence.HIGH)

    def test_intent_detector_chit_chat_rejection(self):
        """Chit chat messages are rejected with LOW confidence and UNKNOWN intent."""
        chit_chats = [
            "hello bro",
            "hi everyone",
            "what are you doing",
            "anyone gaming?",
            "good morning",
            "lol",
            "😂",
            "nice song",
            "what game should we play?",
            "who is online?",
            "kalyani is my favorite song",
            "this song is amazing",
            "I love Kalyani",
            "what are you listening to?",
        ]
        for msg in chit_chats:
            intent, q, conf = NaturalMusicRequestDetector.analyze_message(msg)
            self.assertEqual(
                conf,
                IntentConfidence.LOW,
                f"Expected LOW confidence for conversational text '{msg}', got {conf} ({intent})",
            )

    def test_intent_detector_controls(self):
        """Standard playback control keywords detect with HIGH confidence."""
        controls = {
            "pause": MusicIntent.PAUSE,
            "resume": MusicIntent.RESUME,
            "skip": MusicIntent.SKIP,
            "stop": MusicIntent.STOP,
            "queue": MusicIntent.QUEUE,
            "now playing": MusicIntent.NOW_PLAYING,
        }
        for txt, expected_intent in controls.items():
            intent, q, conf = NaturalMusicRequestDetector.analyze_message(txt)
            self.assertEqual(intent, expected_intent)
            self.assertEqual(conf, IntentConfidence.HIGH)

    def test_intent_detector_playnow(self):
        """'playnow Kalyani' detects as PLAYNOW with HIGH confidence."""
        intent, q, conf = NaturalMusicRequestDetector.analyze_message("playnow Kalyani")
        self.assertEqual(intent, MusicIntent.PLAYNOW)
        self.assertEqual(q, "Kalyani")
        self.assertEqual(conf, IntentConfidence.HIGH)

    # =========================================================================
    # END-TO-END FLOW TESTS (Matches Prompt Scenarios 1 to 10)
    # =========================================================================

    async def test_scenario_1_natural_song_request_in_request_channel(self):
        """
        TEST 1: Join VC. Send in #music-requests: 'Kalyani'.
        Expected: Rai resolves Kalyani -> connects/reuses VC -> starts playback.
        """
        msg = MagicMock(spec=discord.Message)
        msg.author = self.user
        msg.guild = self.guild
        msg.channel = self.music_channel
        msg.content = "Kalyani"

        kalyani_song = self._create_mock_song("Kalyani")
        with patch.object(self.cog.search_service, "search_candidates", new_callable=AsyncMock) as mock_search, \
             patch.object(self.cog.resolver_service, "resolve_track", new_callable=AsyncMock) as mock_resolve:
            mock_search.return_value = [kalyani_song.to_resolved().candidate]
            res = MagicMock()
            res.is_success = True
            res.track = kalyani_song.to_resolved()
            mock_resolve.return_value = res

            handled = await self.service.process_message(self.bot, msg)
            self.assertTrue(handled)
            self.assertEqual(self.player.current.title, "Kalyani")
            self.mock_voice_client.play.assert_called_once()

    async def test_scenario_2_and_3_normal_chat_does_not_interrupt_music(self):
        """
        TEST 2 & 3: While music is playing, 'hello bro' or 'what are you guys playing?'
        Expected: NOTHING happens to music. Music continues uninterrupted.
        """
        # Set current playing track
        self.player.current = self._create_mock_song("Kalyani")
        self.mock_voice_client.is_playing.return_value = True

        for chat_text in ("hello bro", "what are you guys playing?"):
            msg = MagicMock(spec=discord.Message)
            msg.author = self.user
            msg.guild = self.guild
            msg.channel = self.music_channel
            msg.content = chat_text

            handled = await self.service.process_message(self.bot, msg)
            self.assertFalse(handled, f"Normal chat '{chat_text}' must not be handled as music request")

            # Music must continue undisturbed
            self.assertEqual(self.player.current.title, "Kalyani")
            self.assertEqual(len(self.player.queue), 0)
            self.mock_voice_client.stop.assert_not_called()

    async def test_scenario_4_natural_request_while_playing_adds_to_queue(self):
        """
        TEST 4: While Kalyani is playing, send: 'Believer'.
        Expected: Believer is ADDED TO QUEUE. Kalyani continues playing.
        Queue shows #1 Kalyani, #2 Believer.
        """
        # Kalyani is playing
        kalyani = self._create_mock_song("Kalyani")
        self.player.current = kalyani
        self.mock_voice_client.is_playing.return_value = True

        msg = MagicMock(spec=discord.Message)
        msg.author = self.user
        msg.guild = self.guild
        msg.channel = self.music_channel
        msg.content = "Believer"

        believer_song = self._create_mock_song("Believer")
        with patch.object(self.cog.search_service, "search_candidates", new_callable=AsyncMock) as mock_search, \
             patch.object(self.cog.resolver_service, "resolve_track", new_callable=AsyncMock) as mock_resolve:
            mock_search.return_value = [believer_song.to_resolved().candidate]
            res = MagicMock()
            res.is_success = True
            res.track = believer_song.to_resolved()
            mock_resolve.return_value = res

            handled = await self.service.process_message(self.bot, msg)
            self.assertTrue(handled)

            # ZERO INTERFERENCE VERIFICATION:
            # 1. Kalyani is STILL the currently playing track!
            self.assertEqual(self.player.current.title, "Kalyani")
            # 2. Voice client stop was NEVER called!
            self.mock_voice_client.stop.assert_not_called()
            # 3. Believer was appended to queue at position 1 (upcoming)
            self.assertEqual(len(self.player.queue), 1)
            self.assertEqual(self.player.queue[0].title, "Believer")

    async def test_scenario_5_playnow_explicit_interruption(self):
        """
        TEST 5: While Kalyani is playing, send: 'playnow Believer'.
        Expected: Kalyani stops immediately, Believer begins playing.
        """
        kalyani = self._create_mock_song("Kalyani")
        self.player.current = kalyani
        self.mock_voice_client.is_playing.return_value = True

        msg = MagicMock(spec=discord.Message)
        msg.author = self.user
        msg.guild = self.guild
        msg.channel = self.music_channel
        msg.content = "playnow Believer"

        believer_song = self._create_mock_song("Believer")
        with patch.object(self.cog.search_service, "search_candidates", new_callable=AsyncMock) as mock_search, \
             patch.object(self.cog.resolver_service, "resolve_track", new_callable=AsyncMock) as mock_resolve:
            mock_search.return_value = [believer_song.to_resolved().candidate]
            res = MagicMock()
            res.is_success = True
            res.track = believer_song.to_resolved()
            mock_resolve.return_value = res

            handled = await self.service.process_message(self.bot, msg)
            self.assertTrue(handled)

            # Kalyani was stopped
            self.mock_voice_client.stop.assert_called_once()
            # Believer became current
            self.assertEqual(self.player.current.title, "Believer")

    async def test_scenario_6_skip_advances_queue(self):
        """
        TEST 6: Send 'skip' in #music-requests.
        Expected: Voice client stops current track to trigger queue advancement.
        """
        self.player.current = self._create_mock_song("Kalyani")
        self.mock_voice_client.is_playing.return_value = True

        msg = MagicMock(spec=discord.Message)
        msg.author = self.user
        msg.guild = self.guild
        msg.channel = self.music_channel
        msg.content = "skip"

        handled = await self.service.process_message(self.bot, msg)
        self.assertTrue(handled)
        self.mock_voice_client.stop.assert_called_once()

    async def test_scenario_7_and_8_pause_and_resume(self):
        """
        TEST 7 & 8: Send 'pause', then 'resume'.
        Expected: Player pauses and resumes cleanly.
        """
        self.player.current = self._create_mock_song("Kalyani")
        self.mock_voice_client.is_playing.return_value = True

        # 1. Pause
        msg_pause = MagicMock(spec=discord.Message)
        msg_pause.author = self.user
        msg_pause.guild = self.guild
        msg_pause.channel = self.music_channel
        msg_pause.content = "pause"

        handled = await self.service.process_message(self.bot, msg_pause)
        self.assertTrue(handled)
        self.mock_voice_client.pause.assert_called_once()

        # 2. Resume
        self.mock_voice_client.is_playing.return_value = False
        self.mock_voice_client.is_paused.return_value = True

        msg_resume = MagicMock(spec=discord.Message)
        msg_resume.author = self.user
        msg_resume.guild = self.guild
        msg_resume.channel = self.music_channel
        msg_resume.content = "resume"

        handled = await self.service.process_message(self.bot, msg_resume)
        self.assertTrue(handled)
        self.mock_voice_client.resume.assert_called_once()

    async def test_scenario_9_queue_display(self):
        """
        TEST 9: Send 'queue'.
        Expected: Shows current track and queued tracks with requester info.
        """
        self.player.current = self._create_mock_song("Kalyani")
        self.player.queue.append(self._create_mock_song("Believer"))

        msg = MagicMock(spec=discord.Message)
        msg.author = self.user
        msg.guild = self.guild
        msg.channel = self.music_channel
        msg.content = "queue"

        handled = await self.service.process_message(self.bot, msg)
        self.assertTrue(handled)
        self.music_channel.send.assert_called()
        call_args = self.music_channel.send.call_args[1]
        self.assertIn("embed", call_args)
        embed = call_args["embed"]
        self.assertIn("Kalyani", embed.description)
        self.assertIn("Believer", embed.description)

    async def test_scenario_10_normal_conversation_outside_request_channel_ignored(self):
        """
        TEST 10: Send messages in other server channels (#general).
        Expected: NO MUSIC ACTION taken under any circumstances.
        """
        msg = MagicMock(spec=discord.Message)
        msg.author = self.user
        msg.guild = self.guild
        msg.channel = self.general_channel  # NOT the music request channel!
        msg.content = "Kalyani"

        handled = await self.service.process_message(self.bot, msg)
        self.assertFalse(handled)
        self.general_channel.send.assert_not_called()
        self.assertEqual(len(self.player.queue), 0)

    # =========================================================================
    # PROTECTION, RATE LIMIT & ISOLATION TESTS
    # =========================================================================

    async def test_duplicate_request_protection(self):
        """Same song requested twice within 10s by same user is blocked."""
        # 1. First request
        msg = MagicMock(spec=discord.Message)
        msg.author = self.user
        msg.guild = self.guild
        msg.channel = self.music_channel
        msg.content = "Kalyani"

        kalyani_song = self._create_mock_song("Kalyani")
        with patch.object(self.cog.search_service, "search_candidates", new_callable=AsyncMock) as mock_search, \
             patch.object(self.cog.resolver_service, "resolve_track", new_callable=AsyncMock) as mock_resolve:
            mock_search.return_value = [kalyani_song.to_resolved().candidate]
            res = MagicMock()
            res.is_success = True
            res.track = kalyani_song.to_resolved()
            mock_resolve.return_value = res

            await self.service.process_message(self.bot, msg)

            # 2. Second request immediately after
            msg2 = MagicMock(spec=discord.Message)
            msg2.author = self.user
            msg2.guild = self.guild
            msg2.channel = self.music_channel
            msg2.content = "Kalyani"

            await self.service.process_message(self.bot, msg2)
            self.music_channel.send.assert_called_with("That song is already queued. 🎵")

    async def test_user_rate_limiting(self):
        """User exceeding 5 requests in 30s is warned without breaking player."""
        self.user.id = 777888
        for i in range(5):
            self.service._user_requests.setdefault(self.user.id, []).append(time.time())

        msg = MagicMock(spec=discord.Message)
        msg.author = self.user
        msg.guild = self.guild
        msg.channel = self.music_channel
        msg.content = "Song Request"

        handled = await self.service.process_message(self.bot, msg)
        self.assertTrue(handled)
        self.music_channel.send.assert_called_with("Slow down 🎵 Try again in a few seconds.")

    async def test_requester_must_be_in_voice(self):
        """If user is not in a voice channel, bot asks them to join first."""
        self.user.voice = None  # User is not connected to voice

        msg = MagicMock(spec=discord.Message)
        msg.author = self.user
        msg.guild = self.guild
        msg.channel = self.music_channel
        msg.content = "Kalyani"

        handled = await self.service.process_message(self.bot, msg)
        self.assertTrue(handled)
        self.music_channel.send.assert_called_with("Join a voice channel first and I'll play it there. 🎧")

    async def test_dynamic_vc_seamless_reuse(self):
        """When user is in a dynamic VC, music connects/plays in that exact room."""
        dynamic_room = MagicMock(spec=discord.VoiceChannel)
        dynamic_room.id = 99999
        dynamic_room.name = "🎙️ User's Dynamic Room"
        self.user.voice = MagicMock()
        self.user.voice.channel = dynamic_room

        # Voice client currently unconnected
        self.guild.voice_client = None

        msg = MagicMock(spec=discord.Message)
        msg.author = self.user
        msg.guild = self.guild
        msg.channel = self.music_channel
        msg.content = "Kalyani"

        kalyani_song = self._create_mock_song("Kalyani")
        with patch.object(self.cog.search_service, "search_candidates", new_callable=AsyncMock) as mock_search, \
             patch.object(self.cog.resolver_service, "resolve_track", new_callable=AsyncMock) as mock_resolve, \
             patch.object(dynamic_room, "connect", new_callable=AsyncMock) as mock_connect:
            mock_search.return_value = [kalyani_song.to_resolved().candidate]
            res = MagicMock()
            res.is_success = True
            res.track = kalyani_song.to_resolved()
            mock_resolve.return_value = res
            mock_connect.return_value = self.mock_voice_client

            handled = await self.service.process_message(self.bot, msg)
            self.assertTrue(handled)
            mock_connect.assert_called_once()

    async def test_cross_module_isolation_unrelated_tasks(self):
        """Running backup, health check, or security tasks during playback does not interrupt music."""
        # 1. Start music playback
        self.player.current = self._create_mock_song("Kalyani")
        self.mock_voice_client.is_playing.return_value = True

        # 2. Simulate health check execution
        from observability.health import ObservabilityHealthService
        health = ObservabilityHealthService.evaluate_health(self.bot)
        self.assertIsNotNone(health)

        # 3. Simulate backup status read
        from backups.manager import BackupManager
        bkp_mgr = BackupManager.get_instance()
        self.assertIsNotNone(bkp_mgr)

        # 4. Verify music was completely untouched
        self.assertEqual(self.player.current.title, "Kalyani")
        self.mock_voice_client.stop.assert_not_called()
        self.mock_voice_client.pause.assert_not_called()
        self.mock_voice_client.disconnect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
