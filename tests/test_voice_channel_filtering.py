import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import discord
from music_bot.services.voice_service import VoiceManager


class TestVoiceChannelFiltering(unittest.TestCase):
    def setUp(self):
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = 123456789
        self.guild.afk_channel_id = 999999
        self.guild.afk_channel = MagicMock(spec=discord.VoiceChannel, id=999999)
        self.me = MagicMock(spec=discord.Member)
        self.guild.me = self.me

    def _create_mock_vc(self, name, channel_id=1000, category_name=None, can_connect=True, can_speak=True):
        vc = MagicMock(spec=discord.VoiceChannel)
        vc.id = channel_id
        vc.name = name
        vc.guild = self.guild
        if category_name:
            cat = MagicMock(spec=discord.CategoryChannel)
            cat.name = category_name
            vc.category = cat
        else:
            vc.category = None

        perms = MagicMock(spec=discord.Permissions)
        perms.connect = can_connect
        perms.speak = can_speak
        vc.permissions_for.return_value = perms
        return vc

    def test_valid_music_channels(self):
        vc1 = self._create_mock_vc("General")
        vc2 = self._create_mock_vc("Music Lounge")
        vc3 = self._create_mock_vc("Chill Vibes")
        vc4 = self._create_mock_vc("Gaming 1")

        self.assertTrue(VoiceManager.is_valid_music_voice_channel(vc1))
        self.assertTrue(VoiceManager.is_valid_music_voice_channel(vc2))
        self.assertTrue(VoiceManager.is_valid_music_voice_channel(vc3))
        self.assertTrue(VoiceManager.is_valid_music_voice_channel(vc4))

    def test_reject_stat_counter_channels(self):
        stat_names = [
            "🔊 🦋 1 online 🦋 47 members",
            "1 online 47 members",
            "Members: 47",
            "Online: 1",
            "Server Status",
            "Goal: 100 Members",
            "Boost Count: 5",
            "Total Members: 120",
        ]
        for name in stat_names:
            vc = self._create_mock_vc(name)
            self.assertFalse(
                VoiceManager.is_valid_music_voice_channel(vc),
                f"Expected channel '{name}' to be rejected as a stat/counter channel"
            )

    def test_reject_by_category(self):
        vc = self._create_mock_vc("Normal Voice", category_name="Server Status!")
        self.assertFalse(VoiceManager.is_valid_music_voice_channel(vc))

        vc2 = self._create_mock_vc("Room 1", category_name="📊 STATS")
        self.assertFalse(VoiceManager.is_valid_music_voice_channel(vc2))

    def test_reject_afk_channel(self):
        vc = self._create_mock_vc("AFK", channel_id=999999)
        self.assertFalse(VoiceManager.is_valid_music_voice_channel(vc))

    def test_reject_missing_permissions(self):
        vc = self._create_mock_vc("General", can_connect=False)
        self.assertFalse(VoiceManager.is_valid_music_voice_channel(vc))

        vc2 = self._create_mock_vc("General", can_speak=False)
        self.assertFalse(VoiceManager.is_valid_music_voice_channel(vc2))

    def test_reject_non_voice_channel(self):
        txt = MagicMock(spec=discord.TextChannel)
        self.assertFalse(VoiceManager.is_valid_music_voice_channel(txt))

    def test_guardian_loop_does_not_join_when_channel_id_none(self):
        from unittest.mock import PropertyMock
        from music_bot.bot import RaiMusicBot
        bot = RaiMusicBot.__new__(RaiMusicBot)
        bot.is_ready = MagicMock(return_value=True)
        bot.db = MagicMock()
        bot.session_manager = MagicMock()
        
        from music_bot.database.models import MusicGuildSettings
        # Guild has 24/7 enabled but twenty_four_seven_channel_id is None
        g_set = MusicGuildSettings(guild_id=self.guild.id, twenty_four_seven_enabled=True, twenty_four_seven_channel_id=None)
        bot.db.get_all_247_guilds = AsyncMock(return_value=[g_set])
        bot.get_guild = MagicMock(return_value=self.guild)

        # Mock session
        session = MagicMock()
        session.is_intentional_disconnect = False
        bot.session_manager.get_session = AsyncMock(return_value=session)
        bot.session_manager.get_session_sync = MagicMock(return_value=session)
        self.guild.voice_client = None

        # Give guild a voice channel that would have matched the old blind fallback
        stat_vc = self._create_mock_vc("🔊 🦋 1 online 🦋 47 members")
        self.guild.voice_channels = [stat_vc]

        with patch.object(type(bot), "guilds", new_callable=PropertyMock, return_value=[self.guild]):
            with patch("music_bot.services.voice_service.VoiceManager.join_voice_channel", new_callable=AsyncMock) as mock_join:
                import asyncio
                asyncio.run(bot.twenty_four_seven_guardian_loop())
                # Must NOT call join_voice_channel!
                mock_join.assert_not_called()

    def test_guardian_loop_evicts_bot_from_stat_channel(self):
        from unittest.mock import PropertyMock
        from music_bot.bot import RaiMusicBot
        bot = RaiMusicBot.__new__(RaiMusicBot)
        bot.is_ready = MagicMock(return_value=True)
        bot.db = MagicMock()
        bot.session_manager = MagicMock()

        from music_bot.database.models import MusicGuildSettings
        g_set = MusicGuildSettings(guild_id=self.guild.id, twenty_four_seven_enabled=True, twenty_four_seven_channel_id=123)
        bot.db.get_all_247_guilds = AsyncMock(return_value=[g_set])
        bot.get_guild = MagicMock(return_value=self.guild)

        session = MagicMock()
        session.is_intentional_disconnect = False
        bot.session_manager.get_session = AsyncMock(return_value=session)
        bot.session_manager.get_session_sync = MagicMock(return_value=session)

        # Bot is currently connected to a stat channel
        stat_vc = self._create_mock_vc("🔊 🦋 1 online 🦋 47 members")
        mock_voice_client = MagicMock()
        mock_voice_client.is_connected.return_value = True
        mock_voice_client.channel = stat_vc
        self.guild.voice_client = mock_voice_client

        with patch.object(type(bot), "guilds", new_callable=PropertyMock, return_value=[self.guild]):
            with patch("music_bot.services.voice_service.VoiceManager._purge_voice_client_state", new_callable=AsyncMock) as mock_purge:
                import asyncio
                asyncio.run(bot.twenty_four_seven_guardian_loop())
                # Bot MUST be purged/evicted from the stat channel
                mock_purge.assert_called_once_with(self.guild)


if __name__ == "__main__":
    unittest.main()
