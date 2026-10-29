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



@pytest.mark.asyncio
async def test_soundboard_command_plays_track():
    bot = MagicMock(spec=commands.Bot)
    cog = Basic(bot)

    ctx = MagicMock()
    ctx.interaction = MagicMock()
    ctx.interaction.response.is_done.return_value = False
    ctx.defer = AsyncMock()
    ctx.guild.id = 123456789

    mock_channel = MagicMock(spec=discord.VoiceChannel)
    mock_channel.mention = "#general"
    fake_player = MagicMock()
    fake_player.channel = mock_channel
    fake_player.is_playing = False
    fake_player.get_tracks = AsyncMock(return_value=[MagicMock()])
    fake_player.add_track = AsyncMock()
    fake_player.do_next = AsyncMock()
    ctx.guild.voice_client = fake_player

    with pytest.MonkeyPatch.context() as m:
        dispatch_mock = AsyncMock()
        m.setattr("cogs.basic.dispatch_message", dispatch_mock)

        await cog.soundboard.callback(cog, ctx, sound="tuturu")
        ctx.defer.assert_awaited_once()
        fake_player.get_tracks.assert_awaited_once()
        fake_player.add_track.assert_awaited_once()
        fake_player.do_next.assert_awaited_once()
        dispatch_mock.assert_awaited_once()
        assert "Tuturu~" in dispatch_mock.await_args[0][1]

@pytest.mark.asyncio
async def test_aidj_command_toggles_mode():
    bot = MagicMock(spec=commands.Bot)
    cog = Basic(bot)

    ctx = MagicMock()
    ctx.interaction = MagicMock()
    ctx.interaction.response.is_done.return_value = False
    ctx.defer = AsyncMock()
    ctx.guild.id = 123456789

    fake_player = MagicMock()
    fake_player.ai_dj = False
    ctx.guild.voice_client = fake_player

    with pytest.MonkeyPatch.context() as m:
        dispatch_mock = AsyncMock()
        m.setattr("cogs.basic.dispatch_message", dispatch_mock)

        await cog.aidj.callback(cog, ctx, mode="on")
        assert fake_player.ai_dj is True
        dispatch_mock.assert_awaited_once()
        sent_embed = dispatch_mock.await_args[0][1]
        assert "ENABLED" in sent_embed.title

def test_ui_contains_pass_aux_modal_and_10_band_eq():
    # Verify Pass the Aux Modal and priority drop
    assert "openPassTheAuxModal" in UI_HTML
    assert "Pass The Aux — Room Listening Party" in UI_HTML
    assert "submitAuxPriorityDrop" in UI_HTML

    # Verify 10-Band EQ sliders and helpers
    assert "Precision 10-Band Custom Equalizer" in UI_HTML
    assert "applyCustomEqSliders" in UI_HTML
    assert "resetCustomEqSliders" in UI_HTML


@pytest.mark.asyncio
async def test_radio_sleep_vibe_commands():
    bot = MagicMock(spec=commands.Bot)
    cog = Basic(bot)

    ctx = MagicMock()
    ctx.interaction = MagicMock()
    ctx.interaction.response.is_done.return_value = False
    ctx.defer = AsyncMock()
    ctx.guild.id = 123456789

    mock_channel = MagicMock(spec=discord.VoiceChannel)
    mock_channel.mention = "#voice"
    fake_player = MagicMock()
    fake_player.channel = mock_channel
    fake_player.is_playing = False
    fake_player.get_tracks = AsyncMock(return_value=[MagicMock()])
    fake_player.add_track = AsyncMock()
    fake_player.do_next = AsyncMock()
    ctx.guild.voice_client = fake_player

    with pytest.MonkeyPatch.context() as m:
        dispatch_mock = AsyncMock()
        m.setattr("cogs.basic.dispatch_message", dispatch_mock)

        # 1. Test /radio
        await cog.radio.callback(cog, ctx, station="lofi")
        dispatch_mock.assert_awaited()
        assert "Lofi Girl" in dispatch_mock.await_args[0][1]

        # 2. Test /vibe
        await cog.vibe.callback(cog, ctx, mood="anime")
        dispatch_mock.assert_awaited()
        assert "Rem Vibe Matcher" in dispatch_mock.await_args[0][1]

        # 3. Test /sleep
        await cog.sleep.callback(cog, ctx, minutes=15)
        dispatch_mock.assert_awaited()
        assert "15 minutes" in dispatch_mock.await_args[0][1]
