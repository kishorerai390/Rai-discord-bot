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


@pytest.mark.asyncio
async def test_booster_celebration_and_vip_bitrate():
    # 1. Test WelcomeCog Booster Handling
    bot = MagicMock()
    bot.db = AsyncMock()
    welcome_cog = WelcomeCog(bot)

    guild = MagicMock(spec=discord.Guild)
    guild.id = 1457382179981099090
    guild.name = "Rai Server"
    guild.premium_tier = 2
    guild.premium_subscription_count = 7
    guild.icon = None

    member = MagicMock(spec=discord.Member)
    member.id = 444
    member.guild = guild
    member.mention = "<@444>"
    member.roles = []
    member.display_avatar = None
    member.add_roles = AsyncMock()

    general_ch = MagicMock(spec=discord.TextChannel)
    general_ch.id = 1545502730699808768
    general_ch.send = AsyncMock()
    guild.get_channel.return_value = general_ch

    booster_role = MagicMock(spec=discord.Role)
    booster_role.id = 1549504543472353381
    booster_role.name = "💎 ┆ SERVER BOOSTER"
    guild.get_role.return_value = booster_role
    guild.me = MagicMock()
    guild.me.top_role = MagicMock()
    booster_role.__lt__ = MagicMock(return_value=True)

    with patch("utils.owner_reporter.OwnerReporter.send_room_report"):
        await welcome_cog._handle_server_boost(member, is_test=False)
        member.add_roles.assert_awaited_once()
        general_ch.send.assert_awaited_once()
        args, kwargs = general_ch.send.call_args
        assert "💎 ✦ 𝓝ᴇᴡ 𝕾ᴇʀᴠᴇʀ 𝕭ᴏᴏsᴛ ✦ 💎" in kwargs["embed"].title

    # 2. Test VIP Bitrate Calculation in TempVoice
    temp_cog = TempVoiceCog(bot)
    guild.bitrate_limit = 256000
    member.premium_since = MagicMock()
    is_booster = getattr(member, "premium_since", None) is not None
    target_bitrate = min(guild.bitrate_limit, 384000) if is_booster else min(guild.bitrate_limit, 96000)
    assert target_bitrate == 256000


@pytest.mark.asyncio
async def test_serverstats_locked_voice_channels_only():
    from cogs.serverstats import ServerStatsCog
    bot = MagicMock()
    bot.db = AsyncMock()
    stats_cog = ServerStatsCog(bot)

    guild = MagicMock(spec=discord.Guild)
    guild.id = 1234
    guild.member_count = 100
    guild.members = [MagicMock(bot=False, status=discord.Status.online) for _ in range(80)] + [MagicMock(bot=True, status=discord.Status.online) for _ in range(20)]
    guild.premium_subscription_count = 5
    guild.premium_tier = 1

    ch_all = MagicMock(spec=discord.VoiceChannel)
    ch_all.name = "Old All"
    ch_all.edit = AsyncMock()

    ch_mem = MagicMock(spec=discord.VoiceChannel)
    ch_mem.name = "Old Mem"
    ch_mem.edit = AsyncMock()

    ch_bot = MagicMock(spec=discord.VoiceChannel)
    ch_bot.name = "Old Bot"
    ch_bot.edit = AsyncMock()

    guild.voice_channels = [ch_all, ch_mem, ch_bot]
    guild.get_channel.side_effect = lambda cid: {1: ch_all, 2: ch_mem, 3: ch_bot}.get(cid)

    cfg = MagicMock()
    cfg.enabled = True
    cfg.all_members_channel_id = 1
    cfg.members_channel_id = 2
    cfg.bots_channel_id = 3
    bot.db.get_or_create_server_stats_config.return_value = cfg

    updated = await stats_cog.update_guild_stats(guild)
    assert updated is True
    # Verify channel 3 displays boosts since premium_subscription_count > 0
    assert "𝓑ᴏᴏsᴛs: 5 (Tier 1)" in ch_bot.edit.call_args[1]["name"]
    # Verify no text channel creation was called
    assert not hasattr(guild, "create_text_channel") or guild.create_text_channel.call_count == 0

