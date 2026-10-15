"""
Regression Test: Verify MusicCog registers /autodj and other commands without duplicate errors.
Specifically protects against:
discord.app_commands.errors.CommandAlreadyRegistered: Command 'autodj' already registered.
"""

from unittest.mock import AsyncMock, MagicMock, patch
import discord
from discord import app_commands
from discord.ext import commands
import pytest

from music_bot.commands.music_cog import MusicCog


@pytest.mark.asyncio
class TestAutoDJRegistrationRegression:
    """Regression test suite for single-authoritative Auto-DJ command registration."""

    async def test_music_cog_loads_without_duplicate_command_exception(self):
        """1. Verify bot can load MusicCog without CommandAlreadyRegistered or CommandRegistrationError."""
        bot = commands.Bot(command_prefix="m!", intents=discord.Intents.default(), help_command=None)
        bot.db = MagicMock()
        bot.session_manager = MagicMock()

        # Must not raise CommandAlreadyRegistered or CommandRegistrationError
        await bot.add_cog(MusicCog(bot))

        # Check that MusicCog is registered in bot
        cog = bot.get_cog("Music")
        assert cog is not None

    async def test_autodj_slash_command_registered_exactly_once(self):
        """2. Verify /autodj is present in bot.tree exactly once."""
        bot = commands.Bot(command_prefix="m!", intents=discord.Intents.default(), help_command=None)
        bot.db = MagicMock()
        bot.session_manager = MagicMock()
        await bot.add_cog(MusicCog(bot))

        tree_commands = bot.tree.get_commands()
        autodj_cmds = [cmd for cmd in tree_commands if cmd.name == "autodj"]

        assert len(autodj_cmds) == 1, f"Expected exactly 1 /autodj command, found {len(autodj_cmds)}"
        assert autodj_cmds[0].description == "Configure smart automatic music recommendations"

    async def test_autodj_prefix_command_registered_exactly_once_with_aliases(self):
        """3. Verify !autodj prefix command is registered exactly once with expected aliases."""
        bot = commands.Bot(command_prefix="m!", intents=discord.Intents.default(), help_command=None)
        bot.db = MagicMock()
        bot.session_manager = MagicMock()
        await bot.add_cog(MusicCog(bot))

        matching = [cmd for cmd in bot.commands if cmd.name == "autodj"]
        assert len(matching) == 1, f"Expected exactly 1 !autodj command, found {len(matching)}"

        pfx_cmd = matching[0]
        assert set(pfx_cmd.aliases) == {"dj", "autoplay", "nonstop"}

    async def test_autodj_callbacks_and_backward_compatibility(self):
        """4. Verify both cmd_autodj and alias_autodj remain accessible and functional."""
        bot = commands.Bot(command_prefix="m!", intents=discord.Intents.default(), help_command=None)
        bot.db = MagicMock()
        bot.session_manager = MagicMock()
        cog = MusicCog(bot)
        await bot.add_cog(cog)

        assert hasattr(cog, "cmd_autodj")
        assert hasattr(cog, "alias_autodj")
        assert cog.alias_autodj == cog.cmd_autodj

        # Test callback handles string actions
        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.guild_id = 999
        mock_interaction.response.is_done.return_value = False
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.edit_original_response = AsyncMock()

        session = MagicMock()
        session.dj_enabled = False
        session.is_playing = False
        session.now_playing_message = None

        with patch.object(cog.session_manager, "get_session", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = session

            # Turn on
            await cog.cmd_autodj.callback(cog, mock_interaction, action="on")
            assert session.dj_enabled is True
            mock_interaction.edit_original_response.assert_awaited()

            # Turn off
            await cog.cmd_autodj.callback(cog, mock_interaction, action="off")
            assert session.dj_enabled is False

    async def test_other_music_slash_and_prefix_commands_registered(self):
        """5. Verify core music commands still register normally alongside /autodj."""
        bot = commands.Bot(command_prefix="m!", intents=discord.Intents.default(), help_command=None)
        bot.db = MagicMock()
        bot.session_manager = MagicMock()
        await bot.add_cog(MusicCog(bot))

        tree_cmd_names = {cmd.name for cmd in bot.tree.get_commands()}
        pfx_cmd_names = {cmd.name for cmd in bot.commands}

        # Key slash commands
        for cmd_name in ["music", "play", "skip", "queue", "pause", "resume", "stop", "autodj", "voteskip", "mood"]:
            assert cmd_name in tree_cmd_names, f"Expected /{cmd_name} to be in tree commands"

        # Key prefix commands
        for cmd_name in ["play", "skip", "queue", "pause", "resume", "stop", "autodj", "mood"]:
            assert cmd_name in pfx_cmd_names, f"Expected !{cmd_name} to be in prefix commands"
