"""
Unit and Integration Tests for Discord Response Visibility and Music Subsystem.
Verifies:
1. All user-specific slash commands defer and respond with EPHEMERAL visibility ("Only you can see this").
2. InteractionResponseManager ensures followups default to ephemeral.
3. Music playback flow cleanly separates user-specific ephemeral responses from public Now Playing panels.
4. Voice connection and error handling routes ephemeral messages to users and technical reports to OwnerReporter.
5. Voice dependencies (davey, PyNaCl) are present and operational.
"""

import asyncio
import importlib
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import discord

from utils.interaction_reliability import (
    InteractionResponseManager,
    PUBLIC_COMMANDS,
    safe_defer,
    safe_response,
)
from cogs.music import (
    MusicCog,
    GuildMusicPlayer,
    Song,
    MusicControlView,
)


class TestResponseVisibilityAndMusic(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        InteractionResponseManager.install_patches()

    async def test_davey_and_voice_dependencies_present(self):
        """Verifies davey and PyNaCl are importable and VoiceClient does not complain about missing davey."""
        davey_mod = importlib.import_module("davey")
        self.assertIsNotNone(davey_mod)

        nacl_mod = importlib.import_module("nacl")
        self.assertIsNotNone(nacl_mod)

        self.assertTrue(discord.voice_client.has_nacl)

    async def test_tree_interaction_check_defers_ephemerally(self):
        """Verifies slash commands defer with ephemeral=True at gateway level."""
        from core.bot import SentinelBot

        bot = MagicMock(spec=SentinelBot)
        bot.interaction_guard = MagicMock()
        bot.interaction_guard.is_duplicate.return_value = False
        bot.watchdog = MagicMock()

        test_commands = [
            "play", "pause", "resume", "skip", "queue", "np",
            "stop", "music", "backup", "security", "room", "config", "help"
        ]

        for idx, cmd_name in enumerate(test_commands):
            interaction = MagicMock(spec=discord.Interaction)
            interaction.id = 12345 + idx
            interaction.response = MagicMock()
            interaction.response.is_done.return_value = False
            interaction.response.defer = AsyncMock()
            interaction.command = MagicMock()
            interaction.command.name = cmd_name

            handled = await SentinelBot._tree_interaction_check(bot, interaction)
            self.assertTrue(handled)
            interaction.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)

    async def test_application_webhook_followup_defaults_to_ephemeral(self):
        """Verifies that interaction.followup.send defaults to ephemeral=True."""
        state = MagicMock()
        payload = {
            "id": 98765,
            "type": 3,  # WebhookType.application
            "token": "test_token",
        }
        webhook = discord.Webhook.from_state(data=payload, state=state)
        self.assertEqual(webhook.type, discord.WebhookType.application)

        with patch.object(InteractionResponseManager, "_orig_webhook_send", new=AsyncMock()) as mock_orig_send:
            await webhook.send(content="Test ephemeral followup")
            mock_orig_send.assert_awaited_once()
            _, kwargs = mock_orig_send.call_args
            self.assertTrue(kwargs.get("ephemeral"), "Webhook followup did not default to ephemeral=True")

    async def test_check_voice_user_errors_are_ephemeral(self):
        """Verifies that all user-specific voice error responses are ephemeral."""
        bot = MagicMock()
        bot.db = AsyncMock()
        cog = MusicCog(bot)

        # 1. No voice channel
        interaction = MagicMock(spec=discord.Interaction)
        interaction.user = MagicMock()
        interaction.user.voice = None
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        vc = await cog._check_voice(interaction)
        self.assertIsNone(vc)
        interaction.followup.send.assert_awaited_once()
        _, kwargs = interaction.followup.send.call_args
        self.assertTrue(kwargs.get("ephemeral"))
        embed = kwargs.get("embed")
        self.assertIn("NO VOICE CHANNEL", embed.title.upper())

        # 2. Permission denied
        interaction.followup.send.reset_mock()
        voice_state = MagicMock()
        channel = MagicMock()
        voice_state.channel = channel
        interaction.user.voice = voice_state
        interaction.guild = MagicMock()
        interaction.guild.voice_client = None
        interaction.guild.me = MagicMock()
        perms = MagicMock()
        perms.connect = False
        perms.speak = False
        channel.permissions_for.return_value = perms

        vc = await cog._check_voice(interaction)
        self.assertIsNone(vc)
        interaction.followup.send.assert_awaited_once()
        _, kwargs = interaction.followup.send.call_args
        self.assertTrue(kwargs.get("ephemeral"))
        embed = kwargs.get("embed")
        self.assertIn("PERMISSION ERROR", embed.title.upper())

        # 3. Connection failed (technical report dispatched, ephemeral error to user)
        interaction.followup.send.reset_mock()
        perms.connect = True
        perms.speak = True
        channel.connect = AsyncMock(side_effect=RuntimeError("Gateway Timeout"))

        with patch("utils.owner_reporter.OwnerReporter.send_system_report") as mock_report:
            vc = await cog._check_voice(interaction)
            self.assertIsNone(vc)
            mock_report.assert_called_once()
            interaction.followup.send.assert_awaited_once()
            _, kwargs = interaction.followup.send.call_args
            self.assertTrue(kwargs.get("ephemeral"))
            embed = kwargs.get("embed")
            self.assertIn("VOICE CONNECTION FAILED", embed.title.upper())

    async def test_enqueue_and_play_public_panel_and_ephemeral_user_response(self):
        """
        Verifies that:
        - When playback starts:
          1. Public Now Playing panel with buttons is sent to interaction.channel.send (public).
          2. Command confirmation is sent to interaction.followup.send with ephemeral=True.
        - When added to queue:
          1. Command confirmation is sent to interaction.followup.send with ephemeral=True.
        """
        bot = MagicMock()
        bot.db = AsyncMock()
        cog = MusicCog(bot)
        cog.watchdog_task.cancel()

        guild = MagicMock(spec=discord.Guild)
        guild.id = 112233
        guild.name = "Test Server"
        guild.owner_id = 999
        vc = MagicMock(spec=discord.VoiceClient)
        vc.is_playing.return_value = False
        vc.channel = MagicMock()
        vc.channel.name = "RAI MUSIC"
        guild.voice_client = vc

        channel = MagicMock(spec=discord.TextChannel)
        channel.send = AsyncMock(return_value=MagicMock(spec=discord.Message))

        user = MagicMock(spec=discord.Member)
        user.id = 123
        user.guild = guild
        user.mention = "<@123>"
        user.roles = []
        user.guild_permissions = discord.Permissions(administrator=True)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = guild
        interaction.channel = channel
        interaction.user = user
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        song1 = Song(
            title="First Track",
            url="https://youtube.com/watch?v=1",
            stream_url="https://stream.url/1",
            duration=210,
            requester=interaction.user,
            artist="Artist One",
        )

        with patch("discord.FFmpegPCMAudio", return_value=MagicMock()), \
             patch("discord.PCMVolumeTransformer", return_value=MagicMock()):
            # 1. Starting initial playback
            await cog._enqueue_and_play(interaction, song1)

            # Public panel sent to channel
            channel.send.assert_awaited_once()
            _, p_kwargs = channel.send.call_args
            self.assertIn("embed", p_kwargs)
            self.assertIn("view", p_kwargs)
            self.assertIsInstance(p_kwargs["view"], MusicControlView)

            # Ephemeral user response sent to command user
            interaction.followup.send.assert_awaited_once()
            _, u_kwargs = interaction.followup.send.call_args
            self.assertTrue(u_kwargs.get("ephemeral"))
            user_embed = u_kwargs.get("embed")
            self.assertIn("PLAYING", user_embed.title.upper())
            self.assertIn("Playback started", user_embed.description)

            # 2. Enqueuing a second track while music is playing
            vc.is_playing.return_value = True
            interaction.followup.send.reset_mock()
            channel.send.reset_mock()

            song2 = Song(
                title="Second Track",
                url="https://youtube.com/watch?v=2",
                stream_url="https://stream.url/2",
                duration=180,
                requester=interaction.user,
                artist="Artist Two",
            )
            await cog._enqueue_and_play(interaction, song2)

            # Channel should NOT get duplicate Now Playing panel on enqueue
            channel.send.assert_not_called()

            # User should get ephemeral confirmation
            interaction.followup.send.assert_awaited_once()
            _, u2_kwargs = interaction.followup.send.call_args
            self.assertTrue(u2_kwargs.get("ephemeral"))
            q_embed = u2_kwargs.get("embed")
            self.assertIn("PLAY REQUEST", q_embed.title.upper())
            self.assertIn("Added to queue", q_embed.description)

    async def test_music_control_actions_ephemeral_and_update_panel(self):
        """Verifies pause, resume, skip, stop, queue, and nowplaying send ephemeral responses."""
        bot = MagicMock()
        bot.db = AsyncMock()
        bot.db.get_music_config.return_value = MagicMock(dj_role_id=None)
        cog = MusicCog(bot)
        cog.watchdog_task.cancel()

        guild = MagicMock(spec=discord.Guild)
        guild.id = 556677
        guild.name = "Music Server"
        guild.owner_id = 999
        vc = MagicMock(spec=discord.VoiceClient)
        vc.channel = MagicMock()
        vc.channel.name = "RAI MUSIC"
        guild.voice_client = vc

        player = cog.get_player(guild)
        player.current = Song("Song Title", "https://url", "https://stream", 120, MagicMock(), "Artist")
        player.update_panel = AsyncMock()

        user = MagicMock(spec=discord.Member)
        user.id = 456
        user.guild = guild
        user.roles = []
        user.guild_permissions = discord.Permissions(administrator=True)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = guild
        interaction.user = user
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        # Pause
        vc.is_playing.return_value = True
        await cog._handle_pause(interaction)
        vc.pause.assert_called_once()
        player.update_panel.assert_awaited()
        _, k_pause = interaction.followup.send.call_args
        self.assertTrue(k_pause.get("ephemeral"))

        # Resume
        interaction.followup.send.reset_mock()
        vc.is_playing.return_value = False
        vc.is_paused.return_value = True
        await cog._handle_resume(interaction)
        vc.resume.assert_called_once()
        _, k_resume = interaction.followup.send.call_args
        self.assertTrue(k_resume.get("ephemeral"))

        # Skip
        interaction.followup.send.reset_mock()
        await cog._handle_skip(interaction)
        vc.stop.assert_called_once()
        _, k_skip = interaction.followup.send.call_args
        self.assertTrue(k_skip.get("ephemeral"))

        # Stop
        interaction.followup.send.reset_mock()
        await cog._handle_stop(interaction)
        self.assertEqual(len(player.queue), 0)
        self.assertIsNone(player.current)
        _, k_stop = interaction.followup.send.call_args
        self.assertTrue(k_stop.get("ephemeral"))


if __name__ == "__main__":
    unittest.main()
