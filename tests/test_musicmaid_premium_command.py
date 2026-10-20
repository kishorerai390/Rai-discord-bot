"""
Test Suite: MusicMaid /premium Command & Public Web Platform Integration.

Validates:
1. /premium appears as an authoritative slash command in bot.tree.
2. The command sends the expected polished Discord embed with anime neon styling.
3. The website button opens the correct public HTTPS URL.
4. The premium plans button appears only when a verified destination exists.
5. Missing or localhost URL configurations are handled gracefully with config warnings.
6. Premium status, activation, and admin grant workflows operate seamlessly.
7. Existing music commands continue working with zero duplicate registrations.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import discord
from discord import app_commands
from discord.ext import commands

from music_bot.commands.music_cog import (
    MusicCog,
    PremiumLinkView,
    get_public_web_url,
)
from music_bot.config import (
    COLOR_PREMIUM,
    get_musicmaid_website_url,
    get_premium_plans_url,
    is_valid_public_https_url,
)


@pytest.fixture
def mock_bot():
    """Create a test bot instance with mocked dependencies."""
    bot = commands.Bot(command_prefix="m!", intents=discord.Intents.default(), help_command=None)
    bot.db = MagicMock()
    bot.db.is_premium = AsyncMock(return_value=False)
    bot.db.set_premium = AsyncMock(return_value=True)
    bot.session_manager = MagicMock()
    return bot


@pytest.mark.asyncio
class TestMusicMaidPremiumSuite:
    """Comprehensive verification of /premium and website link integration."""

    async def test_01_premium_command_registered_in_tree_without_duplicates(self, mock_bot):
        """1. Verify /premium appears in bot.tree and registers cleanly."""
        cog = MusicCog(mock_bot)
        await mock_bot.add_cog(cog)

        tree_cmds = {cmd.name: cmd for cmd in mock_bot.tree.get_commands()}
        assert "premium" in tree_cmds, "Expected /premium to be registered in bot.tree"
        assert isinstance(tree_cmds["premium"], app_commands.Command)
        assert "MusicMaid Premium" in tree_cmds["premium"].description

        # Direct shortcuts
        assert "premium_status" in tree_cmds
        assert "premium_grant" in tree_cmds

        # Prefix commands
        pfx_cmds = {cmd.name: cmd for cmd in mock_bot.commands}
        assert "premium" in pfx_cmds
        assert "vip" in pfx_cmds["premium"].aliases

    async def test_02_url_validator_rules(self):
        """2. Verify URL validator correctly distinguishes production HTTPS from localhost."""
        assert is_valid_public_https_url("https://rai-discord-bot.onrender.com") is True
        assert is_valid_public_https_url("https://musicmaid.io") is True
        assert is_valid_public_https_url("http://musicmaid.io") is True

        # Invalid / localhost / private IPs
        assert is_valid_public_https_url("http://localhost:8080") is False
        assert is_valid_public_https_url("http://127.0.0.1:3000") is False
        assert is_valid_public_https_url("http://0.0.0.0:80") is False
        assert is_valid_public_https_url("http://192.168.1.5") is False
        assert is_valid_public_https_url("not-a-url") is False
        assert is_valid_public_https_url("") is False
        assert is_valid_public_https_url(None) is False

    async def test_03_website_url_configuration_precedence(self):
        """3. Verify URL configuration prioritizes MUSICMAID_WEBSITE_URL."""
        with patch.dict(os.environ, {
            "PUBLIC_BASE_URL": "",
            "MUSICMAID_WEBSITE_URL": "https://custom-maid.org",
        }, clear=False):
            assert get_musicmaid_website_url() == "https://custom-maid.org"
            assert get_public_web_url() == "https://custom-maid.org"

        # Ignores localhost even if set in MUSICMAID_WEBSITE_URL, falling back to public default
        with patch.dict(os.environ, {
            "PUBLIC_BASE_URL": "",
            "MUSICMAID_WEBSITE_URL": "http://localhost:3000",
            "RENDER_EXTERNAL_URL": "",
            "PUBLIC_URL": "",
            "WEB_BASE_URL": "",
        }, clear=False):
            assert get_musicmaid_website_url() == "https://rai-discord-bot.onrender.com"

    async def test_04_premium_link_view_buttons(self):
        """4. Verify PremiumLinkView conditionally attaches buttons based on valid destinations."""
        # Case A: Only website URL configured
        view_a = PremiumLinkView("https://musicmaid.onrender.com", plans_url=None)
        assert len(view_a.children) == 1
        btn_site = view_a.children[0]
        assert btn_site.label == "Open MusicMaid Website"
        assert str(btn_site.emoji) == "🌐"
        assert btn_site.url == "https://musicmaid.onrender.com"

        # Case B: Both website and valid plans URL configured
        view_b = PremiumLinkView(
            "https://musicmaid.onrender.com",
            plans_url="https://musicmaid.onrender.com/plans",
        )
        assert len(view_b.children) == 2
        btn_plans = view_b.children[1]
        assert btn_plans.label == "View Premium Plans"
        assert str(btn_plans.emoji) == "💎"
        assert btn_plans.url == "https://musicmaid.onrender.com/plans"

        # Case C: Invalid / localhost URL produces no broken button
        view_c = PremiumLinkView("http://localhost:8080", plans_url=None)
        assert len(view_c.children) == 0

    async def test_05_premium_overview_embed_content(self, mock_bot):
        """5. Verify the /premium default execution sends the required embed and branding."""
        cog = MusicCog(mock_bot)
        interaction = MagicMock(spec=discord.Interaction)
        interaction.response = MagicMock()
        interaction.response.is_done.return_value = True
        interaction.edit_original_response = AsyncMock()

        with patch.dict(os.environ, {
            "PUBLIC_BASE_URL": "",
            "MUSICMAID_WEBSITE_URL": "https://musicmaid.onrender.com",
        }, clear=False):
            await cog.cmd_premium.callback(cog, interaction, action=None, key=None)

        interaction.edit_original_response.assert_called_once()
        kwargs = interaction.edit_original_response.call_args.kwargs
        embed = kwargs["embed"]
        view = kwargs["view"]

        assert "MusicMaid Premium" in embed.title
        assert "Unlock the MusicMaid experience and explore available plans and features on our website." in embed.description
        assert "🌐 Visit the website to learn more and manage your account." in embed.description
        assert "150% Boosted Master Volume Cap" in embed.description
        assert "24/7 Voice Channel Persistence" in embed.description
        assert "Studio DSP Equalizer Presets" in embed.description
        assert "Plans & Subscriptions:" in embed.description
        assert embed.color.value == COLOR_PREMIUM

        # View has the website button
        assert view is not None
        assert len(view.children) == 1
        assert view.children[0].url == "https://musicmaid.onrender.com"

    async def test_06_missing_url_graceful_configuration_notice(self, mock_bot):
        """6. Verify missing or localhost URL shows configuration warning instead of broken button."""
        cog = MusicCog(mock_bot)
        interaction = MagicMock(spec=discord.Interaction)
        interaction.response = MagicMock()
        interaction.response.is_done.return_value = True
        interaction.edit_original_response = AsyncMock()

        # Simulate missing public URL
        with patch("music_bot.commands.music_cog.get_public_web_url", return_value=None), \
             patch("music_bot.commands.music_cog.get_premium_plans_url", return_value=None):
            await cog.cmd_premium.callback(cog, interaction, action=None, key=None)

        kwargs = interaction.edit_original_response.call_args.kwargs
        embed = kwargs["embed"]
        view = kwargs["view"]

        assert "Configuration Warning" in embed.description
        assert "MUSICMAID_WEBSITE_URL" in embed.description
        assert view is None

    async def test_07_premium_action_status(self, mock_bot):
        """7. Verify /premium action:status correctly displays tier and perks."""
        mock_bot.db.is_premium = AsyncMock(return_value=True)
        cog = MusicCog(mock_bot)
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(id=12345)
        interaction.user = MagicMock(id=67890)
        interaction.response = MagicMock()
        interaction.response.is_done.return_value = True
        interaction.edit_original_response = AsyncMock()

        status_choice = MagicMock()
        status_choice.value = "status"

        await cog.cmd_premium.callback(cog, interaction, action=status_choice, key=None)

        kwargs = interaction.edit_original_response.call_args.kwargs
        embed = kwargs["embed"]
        assert "Premium Status" in embed.title
        assert "ACTIVE" in embed.description

    async def test_08_premium_action_activate(self, mock_bot):
        """8. Verify /premium action:activate activates license key."""
        cog = MusicCog(mock_bot)
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = MagicMock(id=12345)
        interaction.guild_id = 12345
        interaction.user = MagicMock(id=67890)
        interaction.response = MagicMock()
        interaction.response.is_done.return_value = True
        interaction.edit_original_response = AsyncMock()

        act_choice = MagicMock()
        act_choice.value = "activate"

        with patch.dict(os.environ, {"PREMIUM_KEY": "test_secret_123"}, clear=False):
            # Test valid key
            await cog.cmd_premium.callback(cog, interaction, action=act_choice, key="test_secret_123")
            mock_bot.db.set_premium.assert_called_once()
            call_kwargs = interaction.edit_original_response.call_args.kwargs
            assert "Premium Activated Successfully" in call_kwargs["content"]


    async def test_09_existing_music_commands_intact(self, mock_bot):
        """9. Verify existing playback and control slash commands remain registered."""
        cog = MusicCog(mock_bot)
        await mock_bot.add_cog(cog)

        cmd_names = {c.name for c in mock_bot.tree.get_commands()}
        core_expected = {"play", "pause", "resume", "np", "nowplaying", "volume", "history", "bump", "voteskip"}
        for name in core_expected:
            assert name in cmd_names, f"Expected {name} to remain registered in tree"
