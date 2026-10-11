import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import discord

from cogs.automod import AutoModCog
from cogs.temp_voice import TempVoiceCog
from cogs.welcome import WelcomeCog, build_sticky_banner


@pytest.mark.asyncio
async def test_antiraid_burst_slowmode():
    bot = MagicMock()
    bot.db = AsyncMock()
    cog = AutoModCog(bot)

    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 123456
    channel.name = "general"
    channel.slowmode_delay = 0
    channel.edit = AsyncMock()
    channel.send = AsyncMock()
    
    guild = MagicMock(spec=discord.Guild)
    guild.id = 999
    guild.me = MagicMock()
    perms = MagicMock()
    perms.manage_channels = True
    channel.permissions_for.return_value = perms
    channel.guild = guild

    with patch("utils.owner_reporter.OwnerReporter.send_security_report") as mock_report:
        # Simulate 9 messages in rapid succession -> no trigger
        for _ in range(9):
            await cog._check_channel_burst(channel)
        assert channel.edit.call_count == 0

        # 10th message -> trigger 5s slowmode
        await cog._check_channel_burst(channel)
        assert channel.edit.call_count == 1
        channel.edit.assert_awaited_with(slowmode_delay=5, reason="Anti-Raid: Sudden message velocity burst (>10 msgs in 4s)")
        assert channel.id in cog._channel_slowmode_active
        assert mock_report.call_count == 1


@pytest.mark.asyncio
async def test_smart_afk_voice_inactivity():
    bot = MagicMock()
    bot.db = AsyncMock()
    cog = TempVoiceCog(bot)

    guild = MagicMock(spec=discord.Guild)
    guild.id = 777
    guild.owner_id = 999999
    afk_channel = MagicMock(spec=discord.VoiceChannel)
    afk_channel.id = 8888
    afk_channel.name = "AFK Lounge"
    guild.afk_channel = afk_channel

    vc = MagicMock(spec=discord.VoiceChannel)
    vc.id = 1111
    vc.name = "Chilling"

    member = MagicMock(spec=discord.Member)
    member.id = 555
    member.bot = False
    member.voice = MagicMock()
    member.voice.self_deaf = True
    member.voice.deaf = False
    member.move_to = AsyncMock()

    vc.members = [member]

    # Pre-seed tracker with timestamp 1205 seconds in the past
    past_time = time.monotonic() - 1205.0
    cog._deaf_inactivity_tracker[(vc.id, member.id)] = past_time

    # Fake room model
    room = MagicMock()
    room.voice_channel_id = vc.id
    room.status = "active"
    bot.db.get_all_dynamic_rooms.return_value = [room]
    bot.db.get_temp_voice_config.return_value = MagicMock(hub_channel_id=0, private_hub_channel_id=0)
    guild.voice_channels = [vc]
    guild.get_channel.return_value = vc

    bot.guilds = [guild]

    with patch("utils.owner_reporter.OwnerReporter.send_room_report") as mock_room_report:
        await cog._dynamic_vc_supervisor()
        member.move_to.assert_awaited_once_with(afk_channel, reason="Smart AFK: Deafened/inactive in dynamic room for 20+ minutes")
        assert (vc.id, member.id) not in cog._deaf_inactivity_tracker
        assert mock_room_report.call_count == 1


@pytest.mark.asyncio
async def test_sticky_banner_generation_and_cycle():
    guild = MagicMock(spec=discord.Guild)
    guild.id = 1457382179981099090
    guild.icon = None

    embed, view = build_sticky_banner(guild)
    assert "✦ 𝓡ᴀɪ 𝕱ᴀᴍ ╏ 𝓦ᴇʟᴄᴏᴍᴇ & 𝓠ᴜɪᴄᴋ 𝓝ᴀᴠɪɢᴀᴛɪᴏɴ ✦" in embed.title
    assert len(view.children) == 3

    bot = MagicMock()
    bot.db = AsyncMock()
    welcome_cog = WelcomeCog(bot)

    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 1545502730699808768
    channel.guild = guild
    channel.name = "general-chat"
    channel.send = AsyncMock()
    channel.fetch_message = AsyncMock()

    welcome_cog._sticky_messages[channel.id] = 12345
    old_msg = MagicMock()
    old_msg.delete = AsyncMock()
    channel.fetch_message.return_value = old_msg

    await welcome_cog._refresh_sticky_message(channel)
    old_msg.delete.assert_awaited_once()
    assert channel.send.call_count == 1
    assert welcome_cog._sticky_channels[channel.id] == 0
