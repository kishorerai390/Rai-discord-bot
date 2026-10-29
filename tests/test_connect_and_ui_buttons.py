import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
import discord
from discord.ext import commands

from cogs.basic import Basic
from voicelink import PlayerPlaceholder, Player
from web.ui import UI_HTML

@pytest.mark.asyncio
async def test_connect_command_immediate_deferral_and_channel_fallback():
    bot = MagicMock(spec=commands.Bot)
    bot.cogs = {}
    cog = Basic(bot)

    # 1. Test when ctx is an interaction and user is not in a voice channel
    ctx = MagicMock()
    ctx.interaction = MagicMock()
    ctx.interaction.response.is_done.return_value = False
    ctx.interaction.response.defer = AsyncMock()
    ctx.defer = AsyncMock()
    ctx.author.voice = None
    ctx.guild.id = 123456789

    # Running connect should defer immediately and send a localized noChannel message without crashing
    with pytest.MonkeyPatch.context() as m:
        send_mock = AsyncMock()
        m.setattr("cogs.basic.send_localized_message", send_mock)
        await cog.connect.callback(cog, ctx, channel=None)
        
        ctx.defer.assert_awaited_once()
        send_mock.assert_awaited_once()
        assert send_mock.await_args[0][1] == "voice.connection.noChannel"

@pytest.mark.asyncio
async def test_connect_command_success_with_member_voice():
    bot = MagicMock(spec=commands.Bot)
    cog = Basic(bot)

    ctx = MagicMock()
    ctx.interaction = MagicMock()
    ctx.interaction.response.is_done.return_value = False
    ctx.defer = AsyncMock()
    mock_channel = MagicMock(spec=discord.VoiceChannel)
    ctx.author.voice.channel = mock_channel
    ctx.guild.id = 123456789

    fake_player = MagicMock()
    fake_player.channel = mock_channel

    with pytest.MonkeyPatch.context() as m:
        connect_mock = AsyncMock(return_value=fake_player)
        send_mock = AsyncMock()
        m.setattr("voicelink.connect_channel", connect_mock)
        m.setattr("cogs.basic.send_localized_message", send_mock)

        await cog.connect.callback(cog, ctx, channel=None)
        connect_mock.assert_awaited_once_with(ctx, mock_channel)
        send_mock.assert_awaited_once_with(ctx, "voice.connection.connect", mock_channel)

def test_ui_no_unwired_dummy_buttons_in_core_views():
    # Verify hero play button on vinyl has togglePlayPause
    assert 'id="hero-play-btn" onclick="togglePlayPause()"' in UI_HTML
    
    # Verify recommended mood buttons have quickEnqueueMood
    assert "quickEnqueueMood('Lofi Chill Hip Hop Study Beats')" in UI_HTML
    assert "quickEnqueueMood('Synthwave Retro 80s Cyberpunk Night Drive')" in UI_HTML
    
    # Verify stream playlist buttons have handlers
    assert "quickEnqueueMood('Anime Chill Beats Lofi')" in UI_HTML
    
    # Verify client ID updated to 1556676516274905218
    assert "client_id=1556676516274905218" in UI_HTML
    assert "1418299882950623253" not in UI_HTML

    # Verify public navigation unblocked for /stats, /analytics, /system
    assert "const isOwnerOnlyRoute = ['/owner', '/creator'].includes(path);" in UI_HTML

def test_branding_replaces_legacy_mm_logo():
    bot = MagicMock()
    bot.user.display_avatar.url = "https://cdn.discordapp.com/avatars/1556676516274905218/rem_avatar.png"
    ph = PlayerPlaceholder(bot, None)

    # Inactive track thumbnail must return the bot's avatar, not dIFBwU7
    thumb = ph.track_thumbnail()
    assert "dIFBwU7" not in thumb
    assert thumb == bot.user.display_avatar.url

    # Bot icon must return bot's avatar
    icon = ph.bot_icon()
    assert "dIFBwU7" not in icon
    assert icon == bot.user.display_avatar.url

    # PlayerPlaceholder.replace must clean any legacy dIFBwU7 strings
    cleaned = ph.replace("https://i.imgur.com/dIFBwU7.png", {})
    assert "dIFBwU7" not in cleaned
    assert cleaned == bot.user.display_avatar.url

