"""
Unit & Integration Tests for MusicMaid:
1. /247 UI Error Fix & View Parameter Handling
2. 24/7 Voice Persistence & Inactivity Guards
3. /sandbox Diagnostic Harness, Authorization, Safe Testing & Redaction
"""

import asyncio
import os
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import discord
from discord import app_commands

from music_bot.commands.music_cog import MusicCog, Reconnect247View
from music_bot.commands.sandbox_cog import SandboxCog, redact_sensitive
from music_bot.database import MusicDatabase, MusicGuildSettings
from music_bot.services.session_service import GuildMusicSession, PlaybackState, SessionManager
from music_bot.services.voice_service import VoiceManager


class TestTwentyFourSevenAndSandboxSuite(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db_path = Path(f"test_247_sandbox_{os.getpid()}_{id(self)}.db")
        self.db = MusicDatabase(self.db_path)
        await self.db.connect()

        self.guild_id = 999888777666
        self.channel_id = 111222333444

        # Configure guild settings
        self.settings = MusicGuildSettings(
            guild_id=self.guild_id,
            twenty_four_seven_enabled=False,
            twenty_four_seven_channel_id=None,
            default_volume=100,
        )
        await self.db.update_guild_settings(self.settings)

        # Mock Bot
        self.bot = MagicMock()
        self.bot.db = self.db
        self.bot.is_ready.return_value = True
        self.bot.latency = 0.042
        self.bot.user = MagicMock()
        self.bot.user.id = 1234567890
        self.bot.user.name = "MusicMaid"
        self.bot.voice_clients = []
        self.bot.guilds = []
        self.bot.commands = []

        # Command Tree
        self.bot._connection._command_tree = None
        self.tree = app_commands.CommandTree(self.bot)
        self.bot.tree = self.tree

        # Session Manager & Session
        self.session_manager = SessionManager()
        self.session = GuildMusicSession(self.guild_id)
        self.session_manager._sessions[self.guild_id] = self.session
        self.bot.session_manager = self.session_manager

        # Mock Guild & Channel
        self.channel = MagicMock(spec=discord.VoiceChannel)
        self.channel.id = self.channel_id
        self.channel.name = "General Voice"
        self.channel.mention = "<#111222333444>"
        self.channel.members = []

        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = self.guild_id
        self.guild.name = "Test Discord Server"
        self.guild.owner_id = 999999999
        self.guild.get_channel.return_value = self.channel
        self.guild.voice_channels = [self.channel]
        self.bot.get_guild.return_value = self.guild

        # Voice Client
        self.vc = MagicMock(spec=discord.VoiceClient)
        self.vc.is_connected.return_value = False
        self.vc.is_playing.return_value = False
        self.vc.is_paused.return_value = False
        self.vc.channel = self.channel
        self.vc.disconnect = AsyncMock()
        self.session.voice_client = None

        # Cogs
        self.music_cog = MusicCog(self.bot)
        self.sandbox_cog = SandboxCog(self.bot)

    async def asyncTearDown(self):
        if self.session.auto_leave_task and not self.session.auto_leave_task.done():
            self.session.auto_leave_task.cancel()
        await self.db.close()
        if self.db_path.exists():
            try:
                self.db_path.unlink()
            except OSError:
                pass

    # =========================================================================
    # PHASE 1 TESTS: /247 RESPONSE & VIEW PARAMETER CONTRACT
    # =========================================================================

    async def test_01_twenty_four_seven_status_with_reconnect_view(self):
        """1. /247 status sends valid Reconnect247View when 24/7 is enabled in DB but bot is disconnected."""
        # Enable 24/7 in DB with a channel saved
        self.settings.twenty_four_seven_enabled = True
        self.settings.twenty_four_seven_channel_id = self.channel_id
        await self.db.update_guild_settings(self.settings)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = self.guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.response = MagicMock()
        interaction.response.is_done.return_value = True
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        choice = app_commands.Choice(name="Check 24/7 Status", value="status")
        await self.music_cog.cmd_247.callback(self.music_cog, interaction, action=choice)

        interaction.followup.send.assert_awaited_once()
        _, kwargs = interaction.followup.send.call_args
        self.assertIn("embed", kwargs)
        self.assertIn("view", kwargs)
        self.assertIsInstance(kwargs["view"], Reconnect247View)

    async def test_02_twenty_four_seven_status_without_view(self):
        """2. /247 status omits view parameter completely when 24/7 is disabled or connected."""
        # 24/7 is disabled
        self.settings.twenty_four_seven_enabled = False
        await self.db.update_guild_settings(self.settings)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = self.guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.response = MagicMock()
        interaction.response.is_done.return_value = True
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        choice = app_commands.Choice(name="Check 24/7 Status", value="status")
        await self.music_cog.cmd_247.callback(self.music_cog, interaction, action=choice)

        interaction.followup.send.assert_awaited_once()
        _, kwargs = interaction.followup.send.call_args
        self.assertIn("embed", kwargs)
        # Crucial check: view must NOT be passed when None
        self.assertNotIn("view", kwargs, "followup.send must NOT receive view when None")

    async def test_03_discord_py_view_none_type_error_contract(self):
        """3. Verify discord.py raises TypeError when view=None is explicitly passed, and fixed code avoids it."""
        # Real discord.py Webhook.send logic verification
        webhook = discord.Webhook(data={"id": 1, "token": "dummy", "type": 1}, session=MagicMock())
        with self.assertRaises(TypeError) as ctx:
            # Explicit view=None call
            await webhook.send("Test", view=None)
        self.assertIn("expected view parameter to be of type View or LayoutView, not NoneType", str(ctx.exception))

    async def test_03b_send_ephemeral_or_fallback_safe_with_view_none(self):
        """3b. Verify send_ephemeral_or_fallback safely omits view when view is None."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.response.is_done.return_value = True
        interaction.followup.send = AsyncMock()

        # Calling with view=None must NOT pass view=None to followup.send
        await MusicCog.send_ephemeral_or_fallback(interaction, content="Notice", view=None)
        interaction.followup.send.assert_awaited_once()
        _, kwargs = interaction.followup.send.call_args
        self.assertNotIn("view", kwargs)

    # =========================================================================
    # PHASE 2 TESTS: 24/7 VOICE PERSISTENCE & INACTIVITY GUARDS
    # =========================================================================

    async def test_04_twenty_four_seven_enabled_empty_queue_remains_connected(self):
        """4. 24/7 enabled with empty queue -> schedule_auto_leave is immediately bypassed."""
        self.session.twenty_four_seven = True
        VoiceManager.schedule_auto_leave(self.bot, self.session, timeout=1)
        self.assertIsNone(self.session.auto_leave_task)

    async def test_05_twenty_four_seven_enabled_paused_playback_remains_connected(self):
        """5. 24/7 enabled with paused playback -> remains connected indefinitely."""
        self.session.twenty_four_seven = True
        self.session.state = PlaybackState.PAUSED
        VoiceManager.schedule_auto_leave(self.bot, self.session, timeout=1)
        self.assertIsNone(self.session.auto_leave_task)

    async def test_06_twenty_four_seven_disabled_normal_idle_cleanup(self):
        """6. 24/7 disabled with empty voice channel -> auto-leave task disconnects after timeout."""
        self.session.twenty_four_seven = False
        self.session.voice_client = self.vc
        self.vc.is_connected.return_value = True

        VoiceManager.schedule_auto_leave(self.bot, self.session, timeout=0)
        self.assertIsNotNone(self.session.auto_leave_task)
        await self.session.auto_leave_task

        self.vc.disconnect.assert_awaited_once()

    # =========================================================================
    # PHASE 3 TESTS: /sandbox AUTHORIZATION, SAFE TESTING & REDACTION
    # =========================================================================

    async def test_07_sandbox_authorization_and_denial(self):
        """7. /sandbox access control: ordinary members are denied, owners/admins are permitted."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = self.guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 888888888  # Ordinary user
        interaction.user.guild_permissions.administrator = False
        interaction.response.is_done.return_value = False
        interaction.response.send_message = AsyncMock()

        # Non-admin check
        self.assertFalse(await self.sandbox_cog.is_authorized(interaction))

        # Admin check
        interaction.user.guild_permissions.administrator = True
        self.assertTrue(await self.sandbox_cog.is_authorized(interaction))

        # Test unauthorized denial execution
        interaction.user.guild_permissions.administrator = False
        await self.sandbox_cog.sandbox_list.callback(self.sandbox_cog, interaction)
        interaction.response.send_message.assert_awaited_once()
        denial_msg = interaction.response.send_message.call_args[0][0]
        self.assertIn("Access Denied", denial_msg)

    async def test_08_sandbox_safe_testing_of_supported_commands(self):
        """8. /sandbox test safely executes supported commands, marks mutating ones as UNSUPPORTED, and unknown as FAIL."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = self.guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 999999999  # Guild owner
        interaction.user.guild_permissions.administrator = True
        interaction.response.is_done.return_value = True
        interaction.response.defer = AsyncMock()
        interaction.followup.send = AsyncMock()

        # Register commands on mock tree
        mock_ping = MagicMock()
        mock_ping.name = "ping"
        mock_play = MagicMock()
        mock_play.name = "play"
        self.bot.tree.get_commands = MagicMock(return_value=[mock_ping, mock_play])

        # 1. Test supported command (ping) -> PASS
        await self.sandbox_cog.sandbox_test.callback(self.sandbox_cog, interaction, command="ping")
        embed_ping = interaction.followup.send.call_args[1]["embed"]
        self.assertIn("PASS", embed_ping.fields[0].value)

        # 2. Test mutating command (play) -> UNSUPPORTED (Production Safety)
        interaction.followup.send.reset_mock()
        await self.sandbox_cog.sandbox_test.callback(self.sandbox_cog, interaction, command="play")
        embed_play = interaction.followup.send.call_args[1]["embed"]
        self.assertIn("UNSUPPORTED", embed_play.fields[0].value)

        # 3. Test unknown command (nonexistent) -> FAIL
        interaction.followup.send.reset_mock()
        await self.sandbox_cog.sandbox_test.callback(self.sandbox_cog, interaction, command="nonexistent")
        embed_unknown = interaction.followup.send.call_args[1]["embed"]
        self.assertIn("FAIL", embed_unknown.fields[0].value)

    async def test_09_sandbox_report_redaction_and_concurrency_lock(self):
        """9. /sandbox report: verifies sensitive credentials are redacted and duplicate runs are blocked."""
        # 1. Test sensitive redaction
        # Dynamically construct synthetic token to ensure static secret scanners are not triggered
        dummy_token = ("M" * 25) + "." + ("X" * 6) + "." + ("Y" * 28)
        leak_text = (
            f"Discord Bot Token: {dummy_token}\n"
            "Database URL: sqlite://myuser:supersecretpass@localhost/db\n"
            "Session: rai_session=abc123secrettoken456\n"
            "Secret: client_secret=very_secret_key_here\n"
        )
        sanitized = redact_sensitive(leak_text)
        self.assertNotIn("MMMMMMMMMMMMMMMMMMMMMMMMM", sanitized)
        self.assertNotIn("supersecretpass", sanitized)
        self.assertNotIn("abc123secrettoken456", sanitized)
        self.assertNotIn("very_secret_key_here", sanitized)
        self.assertIn("[REDACTED_DISCORD_TOKEN]", sanitized)
        self.assertIn("[REDACTED_PW]", sanitized)
        self.assertIn("[REDACTED_COOKIE]", sanitized)
        self.assertIn("[REDACTED_SECRET]", sanitized)

        # 2. Test concurrency lock
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = self.guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 999999999
        interaction.user.guild_permissions.administrator = True
        interaction.response.send_message = AsyncMock()

        # Simulate lock already held
        await self.sandbox_cog._report_lock.acquire()
        try:
            await self.sandbox_cog.sandbox_report.callback(self.sandbox_cog, interaction)
            interaction.response.send_message.assert_awaited_once()
            self.assertIn("currently generating", interaction.response.send_message.call_args[0][0])
        finally:
            self.sandbox_cog._report_lock.release()

    async def test_10_sandbox_list_and_health_integration(self):
        """10. /sandbox list and /sandbox health output rich diagnostic status embeds."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = self.guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 999999999
        interaction.user.guild_permissions.administrator = True
        interaction.response.is_done.return_value = True
        interaction.response.defer = AsyncMock()
        interaction.followup.send = AsyncMock()

        # Test health
        await self.sandbox_cog.sandbox_health.callback(self.sandbox_cog, interaction)
        interaction.followup.send.assert_awaited_once()
        embed = interaction.followup.send.call_args[1]["embed"]
        self.assertIn("HEALTH CHECK", embed.title)

        # Test list
        interaction.followup.send.reset_mock()
        await self.sandbox_cog.sandbox_list.callback(self.sandbox_cog, interaction)
        interaction.followup.send.assert_awaited_once()
        list_embed = interaction.followup.send.call_args[1]["embed"]
        self.assertIn("REGISTERED COMMANDS", list_embed.title)


if __name__ == "__main__":
    unittest.main()
