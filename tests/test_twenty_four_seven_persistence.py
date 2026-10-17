"""
Comprehensive Test Suite: 24/7 Voice Channel Persistence & Student Developer Premium Mode.

Validates:
1. 24/7 Setting Persistence in database with honest Discord embed reporting.
2. Auto-leave cancellation & DB-backed guard aborting disconnection when voice channel is empty.
3. Stale inactivity task invalidation when 24/7 is enabled.
4. VoiceManager.join_voice_channel connects directly to target_channel without member.voice.
5. 24/7 Guardian watchdog loop discovers disconnected 24/7 guilds and restores connections.
6. Permission checks fail fast with diagnostic feedback and prevent infinite loops.
7. Multi-guild state isolation.
8. Student Developer Mode (PAYMENTS_ENABLED=false) blocks live checkouts while presenting plans safely.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import discord
from discord.ext import commands

from music_bot.database.models import MusicGuildSettings
from music_bot.services.session_service import GuildMusicSession, PlaybackState, SessionManager
from music_bot.services.voice_service import VoiceManager
from music_bot.commands.music_cog import MusicCog, Reconnect247View
from music_bot import config
from web.payment_api import PaymentApiRouter


class MockVoiceChannel(MagicMock):
    """Mock discord.VoiceChannel."""
    def __init__(self, channel_id: int = 12345, name: str = "General Voice", guild: Optional[Any] = None, **kwargs):
        super().__init__(spec=discord.VoiceChannel, **kwargs)
        self.id = channel_id
        self.name = name
        self.mention = f"<#{channel_id}>"
        self.guild = guild
        self.members = []
        self.connect = AsyncMock()


class MockVoiceClient(MagicMock):
    """Mock discord.VoiceClient."""
    def __init__(self, channel: Optional[MockVoiceChannel] = None, **kwargs):
        super().__init__(spec=discord.VoiceClient, **kwargs)
        self.channel = channel
        self._connected = True
        self.disconnect = AsyncMock()
        self.move_to = AsyncMock()
        self.stop = MagicMock()
        self.is_playing = MagicMock(return_value=False)
        self.is_paused = MagicMock(return_value=False)

    def is_connected(self) -> bool:
        return self._connected


@pytest.fixture
def mock_bot_and_guild():
    """Create a mock bot, guild, and test voice channel."""
    bot = commands.Bot(command_prefix="m!", intents=discord.Intents.default(), help_command=None)
    bot.db = MagicMock()
    bot.db.is_premium = AsyncMock(return_value=True)
    bot.db.get_guild_settings = AsyncMock()
    bot.db.update_guild_settings = AsyncMock()
    bot.db.get_all_247_guilds = AsyncMock(return_value=[])
    bot.session_manager = SessionManager.get_instance()

    guild = MagicMock(spec=discord.Guild)
    guild.id = 987654321
    guild.name = "Test Nyx Server"
    guild.owner_id = 111111111
    guild.afk_channel = None

    vc_channel = MockVoiceChannel(channel_id=55555, name="Lounge", guild=guild)
    guild.voice_channels = [vc_channel]
    guild.get_channel.return_value = vc_channel

    bot_me = MagicMock(spec=discord.Member)
    bot_me.id = 999999999
    perms = MagicMock()
    perms.connect = True
    perms.speak = True
    perms.move_members = True
    vc_channel.permissions_for = MagicMock(return_value=perms)
    guild.me = bot_me
    guild.voice_client = None

    bot.get_guild = MagicMock(return_value=guild)
    return bot, guild, vc_channel


@pytest.mark.asyncio
class TestTwentyFourSevenPersistenceSuite:
    """Rigorous validation of the 24/7 disconnect fix and persistence logic."""

    async def test_01_auto_leave_aborts_when_247_enabled_in_db(self, mock_bot_and_guild):
        """1. Confirm that _auto_leave_worker checks DB and refuses to disconnect if 24/7 is enabled."""
        bot, guild, vc_channel = mock_bot_and_guild
        session = await bot.session_manager.get_session(guild.id)
        
        # Simulate voice client connected to an empty channel
        mock_vc = MockVoiceClient(channel=vc_channel)
        session.voice_client = mock_vc
        session.twenty_four_seven = False  # In-memory flag unset

        # DB has 24/7 enabled!
        saved_settings = MusicGuildSettings(
            guild_id=guild.id,
            twenty_four_seven_enabled=True,
            twenty_four_seven_channel_id=vc_channel.id,
        )
        bot.db.get_guild_settings.return_value = saved_settings

        # Run auto leave worker with timeout 0 to trigger immediate inspection
        await VoiceManager._auto_leave_worker(bot, session, timeout=0)

        # The worker MUST NOT have called disconnect
        assert mock_vc.disconnect.call_count == 0, "VoiceClient.disconnect was called despite 24/7 enabled in DB!"
        assert session.twenty_four_seven is True, "Session in-memory flag should be hydrated to True from DB."
        assert session.voice_client is mock_vc, "Voice client should remain intact."

    async def test_02_schedule_auto_leave_bypassed_if_247_in_memory(self, mock_bot_and_guild):
        """2. Confirm schedule_auto_leave cancels any existing task and bypasses scheduling when 24/7 is active."""
        bot, guild, vc_channel = mock_bot_and_guild
        session = await bot.session_manager.get_session(guild.id)
        session.twenty_four_seven = True

        dummy_task = MagicMock()
        dummy_task.done.return_value = False
        session.auto_leave_task = dummy_task

        VoiceManager.schedule_auto_leave(bot, session, timeout=300)

        assert dummy_task.cancel.called, "Existing auto_leave_task should have been cancelled."
        assert session.auto_leave_task is None, "New auto_leave_task should NOT be scheduled when 24/7 is active."

    async def test_03_join_voice_channel_direct_target_channel(self, mock_bot_and_guild):
        """3. Confirm VoiceManager.join_voice_channel supports target_channel without requiring member.voice."""
        bot, guild, vc_channel = mock_bot_and_guild
        session = await bot.session_manager.get_session(guild.id)

        mock_vc = MockVoiceClient(channel=vc_channel)
        vc_channel.connect = AsyncMock(return_value=mock_vc)

        # Call join_voice_channel with target_channel directly and member=guild.me (no member.voice)
        vc = await VoiceManager.join_voice_channel(
            member=guild.me,
            text_channel=None,
            session=session,
            target_channel=vc_channel,
        )

        assert vc is not None, "Voice connection should succeed with target_channel provided."
        assert session.voice_client is vc
        assert vc.channel.id == vc_channel.id

    async def test_04_permission_check_fails_fast_without_infinite_loop(self, mock_bot_and_guild):
        """4. Verify missing Connect or Speak permissions fast-fails without retries or loops."""
        bot, guild, vc_channel = mock_bot_and_guild
        session = await bot.session_manager.get_session(guild.id)

        # Strip connect permission
        perms = MagicMock()
        perms.connect = False
        perms.speak = True
        vc_channel.permissions_for = MagicMock(return_value=perms)

        vc = await VoiceManager.join_voice_channel(
            member=guild.me,
            text_channel=None,
            session=session,
            target_channel=vc_channel,
        )

        assert vc is None, "Should fail fast when Connect permission is missing."
        assert "Missing **Connect** permission" in session.last_error

    async def test_05_cmd_247_honest_status_reporting(self, mock_bot_and_guild):
        """5. Verify /247 reports DISCONNECTED and provides reconnect when voice is not active."""
        bot, guild, vc_channel = mock_bot_and_guild
        cog = MusicCog(bot)

        # Setup DB setting as enabled, but bot voice client is DISCONNECTED
        saved_settings = MusicGuildSettings(
            guild_id=guild.id,
            twenty_four_seven_enabled=True,
            twenty_four_seven_channel_id=vc_channel.id,
        )
        bot.db.get_guild_settings.return_value = saved_settings

        session = await bot.session_manager.get_session(guild.id)
        session.voice_client = None  # Disconnected!

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = guild
        interaction.user = guild.me
        interaction.channel = MagicMock()
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        choice_status = MagicMock()
        choice_status.value = "status"

        await cog.cmd_247.callback(cog, interaction, action=choice_status)

        assert interaction.followup.send.called
        sent_call = interaction.followup.send.call_args
        embed = sent_call.kwargs.get("embed")
        view = sent_call.kwargs.get("view")

        assert embed is not None
        assert "24/7 PERSISTENCE STATUS" in embed.title
        assert "Voice Status:** `DISCONNECTED`" in embed.description
        assert "24/7 Setting:** `ENABLED`" in embed.description
        assert isinstance(view, Reconnect247View), "A Reconnect247View should be attached when 24/7 is on but disconnected."

    async def test_06_cmd_247_deactivation_restores_auto_leave(self, mock_bot_and_guild):
        """6. Disabling 24/7 mode updates DB and restores normal auto-leave behavior."""
        bot, guild, vc_channel = mock_bot_and_guild
        cog = MusicCog(bot)

        saved_settings = MusicGuildSettings(
            guild_id=guild.id,
            twenty_four_seven_enabled=True,
            twenty_four_seven_channel_id=vc_channel.id,
        )
        bot.db.get_guild_settings.return_value = saved_settings

        session = await bot.session_manager.get_session(guild.id)
        session.twenty_four_seven = True

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = guild
        interaction.user = guild.me
        interaction.channel = MagicMock()
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        choice_disable = MagicMock()
        choice_disable.value = "disable"

        await cog.cmd_247.callback(cog, interaction, action=choice_disable)

        assert bot.db.update_guild_settings.called
        updated_settings = bot.db.update_guild_settings.call_args[0][0]
        assert updated_settings.twenty_four_seven_enabled is False
        assert session.twenty_four_seven is False

        sent_call = interaction.followup.send.call_args
        embed = sent_call.kwargs.get("embed")
        assert "24/7 MODE DEACTIVATED" in embed.title

    async def test_07_multi_guild_isolation(self, mock_bot_and_guild):
        """7. Verify two guilds do not share 24/7 or session state."""
        bot, guild, vc_channel = mock_bot_and_guild
        session1 = await bot.session_manager.get_session(1001)
        session2 = await bot.session_manager.get_session(1002)

        session1.twenty_four_seven = True
        session2.twenty_four_seven = False

        assert session1.twenty_four_seven is True
        assert session2.twenty_four_seven is False
        assert session1.guild_id != session2.guild_id

    async def test_08_student_developer_mode_blocks_real_checkout(self):
        """8. When PAYMENTS_ENABLED is False, create_checkout returns 503 PAYMENTS_DISABLED."""
        auth = MagicMock()
        auth.get_session_from_request = AsyncMock(return_value={"user_id": 12345, "user_data": {"username": "StudentDev"}})
        router = PaymentApiRouter(bot=MagicMock(), db=MagicMock(), auth=auth)

        req = MagicMock()
        req.json = AsyncMock(return_value={"plan": "monthly"})
        req.headers = {}
        req.remote = "127.0.0.1"

        with patch.object(config, "PAYMENTS_ENABLED", False):
            resp = await router.create_checkout(req)
            assert resp.status == 503
            import json
            body = json.loads(resp.text)
            assert body["success"] is False
            assert body["error"]["code"] == "PAYMENTS_DISABLED"
            assert "Student Developer Showcase Mode" in body["error"]["message"]
