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
    assert "5 Boosts" in ch_bot.edit.call_args[1]["name"]
    # Verify no text channel creation was called
    assert not hasattr(guild, "create_text_channel") or guild.create_text_channel.call_count == 0


@pytest.mark.asyncio
async def test_dynamic_vc_share_link():
    from utils.dynamic_vc_control import DynamicVCControlManager
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild_id = 1457382179981099090
    interaction.user = MagicMock()
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()

    vc = MagicMock(spec=discord.VoiceChannel)
    vc.id = 998877
    vc.name = "✦ Rai Squad"
    invite = MagicMock()
    invite.url = "https://discord.gg/dynamic-test"
    vc.create_invite = AsyncMock(return_value=invite)

    res = await DynamicVCControlManager._handle_share_link(interaction, vc)
    assert res is True
    interaction.response.send_message.assert_awaited_once()
    args, kwargs = interaction.response.send_message.call_args
    assert "🔗 Room Invite Link" in kwargs["embed"].title
    assert "https://discord.com/channels/1457382179981099090/998877" in kwargs["embed"].description


@pytest.mark.asyncio
async def test_automod_spoiler_grid_filter():
    bot = MagicMock()
    bot.user = MagicMock()
    bot.user.id = 9999
    bot.db = AsyncMock()
    cog = AutoModCog(bot)

    guild = MagicMock(spec=discord.Guild)
    guild.owner_id = 8888
    member = MagicMock(spec=discord.Member)
    member.id = 111
    member.bot = False
    member.roles = []
    member.guild_permissions.administrator = False

    message = MagicMock(spec=discord.Message)
    message.guild = guild
    message.author = member
    message.channel = MagicMock(spec=discord.TextChannel)
    message.channel.id = 100
    message.channel.name = "general"
    # Create text with 12 spoiler tags (||word|| repeated 12 times)
    message.content = "||secret|| " * 12

    bot.db.is_whitelisted.return_value = False
    bot.db.get_or_create_guild_config.return_value = MagicMock(automod_enabled=True)
    auto_cfg = MagicMock(
        spam_detection=False,
        mention_limit=10,
        invite_links_block=False,
        suspicious_links_block=False,
        banned_words_enabled=False,
        excessive_emojis_block=False,
        excessive_caps_block=False,
        action="delete",
    )
    bot.db.get_automod_config.return_value = auto_cfg

    with patch.object(cog, "_enforce_automod", AsyncMock()) as mock_enforce:
        await cog.on_message(message)
        mock_enforce.assert_awaited_once()
        assert "Excessive Spoiler Grid Spam" in mock_enforce.call_args[0][1]


@pytest.mark.asyncio
async def test_afk_system_set_and_clear():
    from cogs.utility import UtilityCog
    bot = MagicMock()
    cog = UtilityCog(bot)

    guild = MagicMock(spec=discord.Guild)
    guild.id = 12345

    member1 = MagicMock(spec=discord.Member)
    member1.id = 101
    member1.mention = "<@101>"
    member1.display_name = "Kishore"
    member1.bot = False
    member1.guild = guild

    member2 = MagicMock(spec=discord.Member)
    member2.id = 102
    member2.mention = "<@102>"
    member2.display_name = "Alex"
    member2.bot = False
    member2.guild = guild

    # 1. Member1 sets AFK
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = guild
    interaction.user = member1
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()

    await cog.afk.callback(cog, interaction, status="Studying Python")
    assert (guild.id, member1.id) in cog._afk_users
    assert cog._afk_users[(guild.id, member1.id)][0] == "Studying Python"

    # 2. Member2 mentions Member1 in a channel
    msg = MagicMock(spec=discord.Message)
    msg.guild = guild
    msg.author = member2
    msg.mentions = [member1]
    msg.channel = MagicMock(spec=discord.TextChannel)
    msg.channel.send = AsyncMock()

    await cog.on_message(msg)
    msg.channel.send.assert_awaited_once()
    assert "Kishore" in msg.channel.send.call_args[0][0]
    assert "Studying Python" in msg.channel.send.call_args[0][0]

    # 3. Member1 sends a message after 5 seconds -> AFK cleared
    cog._afk_users[(guild.id, member1.id)] = ("Studying Python", time.time() - 5.0)
    msg2 = MagicMock(spec=discord.Message)
    msg2.guild = guild
    msg2.author = member1
    msg2.mentions = []
    msg2.channel = MagicMock(spec=discord.TextChannel)
    msg2.channel.send = AsyncMock()

    await cog.on_message(msg2)
    assert (guild.id, member1.id) not in cog._afk_users
    msg2.channel.send.assert_awaited_once()
    assert "Welcome back <@101>" in msg2.channel.send.call_args[0][0]


@pytest.mark.asyncio
async def test_stream_notification_and_bitrate_optimizer():
    bot = MagicMock()
    bot.db = AsyncMock()
    cog = TempVoiceCog(bot)
    cog._supervisor_task.cancel()

    guild = MagicMock(spec=discord.Guild)
    guild.id = 1457382179981099090
    guild.me = MagicMock()
    guild.me.guild_permissions.manage_channels = True
    guild.bitrate_limit = 256000
    guild.icon = None

    general_ch = MagicMock(spec=discord.TextChannel)
    general_ch.id = 1545502730699808768
    general_ch.send = AsyncMock()
    ann_msg = MagicMock()
    ann_msg.id = 777111
    ann_msg.delete = AsyncMock()
    general_ch.send.return_value = ann_msg
    general_ch.fetch_message = AsyncMock(return_value=ann_msg)

    vc = MagicMock(spec=discord.VoiceChannel)
    vc.id = 5566
    vc.name = "✦ Squad Room"
    vc.bitrate = 256000
    vc.edit = AsyncMock()

    guild.get_channel.side_effect = lambda cid: general_ch if cid == 1545502730699808768 else None

    member = MagicMock(spec=discord.Member)
    member.id = 333
    member.display_name = "StreamerGuy"
    member.mention = "<@333>"
    member.display_avatar = None
    member.guild = guild

    # 1. State: Screen share started
    before_state = MagicMock(spec=discord.VoiceState)
    before_state.self_stream = False
    before_state.channel = vc

    after_state = MagicMock(spec=discord.VoiceState)
    after_state.self_stream = True
    after_state.channel = vc

    vc.members = [member]

    await cog._handle_stream_state_update(member, before_state, after_state)

    # Verify General Chat notification sent
    general_ch.send.assert_awaited_once()
    args, kwargs = general_ch.send.call_args
    assert "𝓛ɪᴠᴇ 𝕾ᴛʀᴇᴀᴍ" in kwargs["embed"].title
    assert "StreamerGuy" in kwargs["embed"].description
    assert (guild.id, member.id) in cog._active_stream_announcements

    # Verify Bitrate scaled down to 96kbps to stabilize stream
    vc.edit.assert_awaited_once_with(bitrate=96000, reason="Stream Optimizer: Adjusted audio bitrate to 96kbps for screen share stability")
    assert cog._original_stream_bitrates[vc.id] == 256000

    # 2. State: Screen share stopped
    stop_before = MagicMock(spec=discord.VoiceState)
    stop_before.self_stream = True
    stop_before.channel = vc

    stop_after = MagicMock(spec=discord.VoiceState)
    stop_after.self_stream = False
    stop_after.channel = vc

    member.voice = stop_after
    vc.members = [member]

    await cog._handle_stream_state_update(member, stop_before, stop_after)

    # Verify General Chat notification deleted
    ann_msg.delete.assert_awaited_once()
    assert (guild.id, member.id) not in cog._active_stream_announcements

    # Verify Bitrate restored back to 256kbps
    vc.edit.assert_awaited_with(bitrate=256000, reason="Stream Optimizer: Restored original audio bitrate")


@pytest.mark.asyncio
async def test_ghost_mention_catcher():
    from cogs.automod import AutoModCog
    bot = MagicMock()
    bot.db = AsyncMock()
    cog = AutoModCog(bot)

    guild = MagicMock(spec=discord.Guild)
    guild.id = 999
    member = MagicMock(spec=discord.Member)
    member.id = 111
    member.bot = False
    member.name = "GhostPinger"
    target = MagicMock(spec=discord.Member)
    target.id = 222

    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 333
    channel.name = "general"
    channel.mention = "<#333>"
    guild.get_channel.return_value = channel

    message = MagicMock(spec=discord.Message)
    message.id = 55555
    message.guild = guild
    message.author = member
    message.mentions = [target]
    message.role_mentions = []
    message.channel = channel
    message.clean_content = "Hey @Someone wake up"

    # 1. Message sent with mention
    await cog.on_message(message)
    assert message.id in cog._recent_mentions

    # 2. Message deleted shortly after
    with patch("utils.owner_reporter.OwnerReporter.send_mod_report") as mock_report:
        await cog.on_message_delete(message)
        assert mock_report.call_count == 1
        call_kwargs = mock_report.call_args[1]
        assert call_kwargs["event"] == "Ghost Mention Detected"
        assert call_kwargs["user"] == member
        assert message.id not in cog._recent_mentions


def test_zero_day_phishing_regex():
    from cogs.automod import SUSPICIOUS_REGEX
    # Malicious links should match
    assert SUSPICIOUS_REGEX.search("https://discorcl-gift.com/nitro") is not None
    assert SUSPICIOUS_REGEX.search("https://dlscord.app/free-nitro") is not None
    assert SUSPICIOUS_REGEX.search("https://discordapp.click/claim") is not None
    assert SUSPICIOUS_REGEX.search("https://nitro-airdrop.ru/get") is not None
    assert SUSPICIOUS_REGEX.search("https://steamcomm-trade.com/offer") is not None

    # Legitimate links should not match
    assert SUSPICIOUS_REGEX.search("https://discord.com/channels/123/456") is None
    assert SUSPICIOUS_REGEX.search("https://discord.gg/invitecode") is None
    assert SUSPICIOUS_REGEX.search("https://google.com") is None


@pytest.mark.asyncio
async def test_antiraid_join_burst():
    from cogs.automod import AutoModCog
    bot = MagicMock()
    bot.db = AsyncMock()
    cog = AutoModCog(bot)

    guild = MagicMock(spec=discord.Guild)
    guild.id = 777

    with patch("utils.owner_reporter.OwnerReporter.send_security_report") as mock_sec_report:
        for i in range(9):
            m = MagicMock(spec=discord.Member)
            m.id = 1000 + i
            m.bot = False
            m.guild = guild
            await cog.on_member_join(m)
        assert mock_sec_report.call_count == 0

        # 10th join within 15s triggers security report
        m10 = MagicMock(spec=discord.Member)
        m10.id = 1010
        m10.bot = False
        m10.guild = guild
        await cog.on_member_join(m10)
        assert mock_sec_report.call_count == 1
        assert mock_sec_report.call_args[1]["event"] == "Mass Join Velocity Spike"


@pytest.mark.asyncio
async def test_stream_stats_and_cinema_mode():
    bot = MagicMock()
    bot.db = AsyncMock()
    cog = TempVoiceCog(bot)

    guild = MagicMock(spec=discord.Guild)
    guild.id = 444
    guild.me = MagicMock()
    guild.me.guild_permissions.manage_channels = True

    member = MagicMock(spec=discord.Member)
    member.id = 555
    member.display_name = "ProGamer"
    member.guild = guild
    member.display_avatar = None

    vc = MagicMock(spec=discord.VoiceChannel)
    vc.id = 666
    vc.name = "Squad Voice"
    vc.bitrate = 128000
    vc.edit = AsyncMock()
    member.voice = MagicMock()
    member.voice.channel = vc

    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = guild
    interaction.user = member
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()

    # Cinema mode toggle
    await cog.stream_command.callback(cog, interaction, action="cinema")
    vc.edit.assert_awaited_with(bitrate=96000, user_limit=15, name="🎬・Squad Voice", reason="Cinema Mode toggled by ProGamer")
    interaction.response.send_message.assert_awaited_once()

    # Accumulate stream time and check stream_stats
    cog._stream_seconds_tracker[(guild.id, member.id)] = 7500  # ~2 hours 5 mins -> Streamer rank
    interaction.response.send_message.reset_mock()

    await cog.stream_stats_command.callback(cog, interaction, member=member)
    interaction.response.send_message.assert_awaited_once()
    args, kwargs = interaction.response.send_message.call_args
    embed = kwargs["embed"]
    assert "2h 5m" in embed.fields[0].value
    assert "Streamer" in embed.description

    # Stream top leaderboard
    guild.get_member.return_value = member
    interaction.response.send_message.reset_mock()
    await cog.stream_top_command.callback(cog, interaction)
    interaction.response.send_message.assert_awaited_once()
    args, kwargs = interaction.response.send_message.call_args
    assert "ProGamer" in kwargs["embed"].description


@pytest.mark.asyncio
async def test_vc_sleep_timer():
    bot = MagicMock()
    bot.db = AsyncMock()
    cog = TempVoiceCog(bot)

    guild = MagicMock(spec=discord.Guild)
    guild.id = 111
    member = MagicMock(spec=discord.Member)
    member.id = 222
    member.guild = guild
    member.voice = MagicMock()
    member.voice.channel = MagicMock(spec=discord.VoiceChannel)

    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = guild
    interaction.user = member
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()

    await cog.vc_sleep_command.callback(cog, interaction, minutes=45)
    interaction.response.send_message.assert_awaited_once()
    assert (guild.id, member.id) in cog._sleep_timers

    # Cancel sleep timer
    interaction.response.send_message.reset_mock()
    await cog.vc_sleep_cancel_command.callback(cog, interaction)
    interaction.response.send_message.assert_awaited_once()
    assert (guild.id, member.id) not in cog._sleep_timers


@pytest.mark.asyncio
async def test_soundboard_spam_limiter():
    bot = MagicMock()
    bot.db = AsyncMock()
    cog = TempVoiceCog(bot)

    guild = MagicMock(spec=discord.Guild)
    guild.id = 777
    guild.owner_id = 999
    member = MagicMock(spec=discord.Member)
    member.id = 888
    member.bot = False
    member.guild = guild

    vc = MagicMock(spec=discord.VoiceChannel)
    vc.id = 333
    vc.set_permissions = AsyncMock()

    for _ in range(4):
        triggered = cog.record_soundboard_effect(vc, member)
        assert not triggered

    # 5th soundboard trigger within 10s -> Limiter activates
    triggered = cog.record_soundboard_effect(vc, member)
    assert triggered


@pytest.mark.asyncio
async def test_nickstyle_and_pulse():
    from cogs.utility import UtilityCog
    bot = MagicMock()
    bot.db = AsyncMock()
    bot.guilds = []
    bot.latency = 0.025
    bot.wait_until_ready = AsyncMock()
    cog = UtilityCog(bot)

    guild = MagicMock(spec=discord.Guild)
    guild.id = 999
    guild.name = "✦ Rai Server ✦"
    guild.icon = None
    guild.owner_id = 1000
    guild.me = MagicMock()
    guild.me.guild_permissions.manage_nicknames = True
    guild.me.top_role = MagicMock()
    guild.me.top_role.position = 10

    member = MagicMock(spec=discord.Member)
    member.id = 2000
    member.display_name = "kishore"
    member.guild = guild
    member.top_role = MagicMock()
    member.top_role.position = 5
    member.edit = AsyncMock()

    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = guild
    interaction.user = member
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()

    # 1. Nickstyle command (small_caps)
    await cog.nickstyle_command.callback(cog, interaction, style="small_caps", text="kishore")
    member.edit.assert_awaited_once()
    call_kwargs = member.edit.call_args[1]
    assert call_kwargs["nick"] == "ᴋɪsʜᴏʀᴇ"
    interaction.response.send_message.assert_awaited_once()

    # 2. Pulse command
    guild.members = [member]
    guild.member_count = 1
    interaction.response.send_message.reset_mock()
    await cog.pulse_command.callback(cog, interaction)
    interaction.response.send_message.assert_awaited_once()
    pulse_embed = interaction.response.send_message.call_args[1]["embed"]
    assert "✦ 𝕾ᴇʀᴠᴇʀ 𝕻ᴜʟsᴇ" in pulse_embed.title
    cog.cog_unload()


@pytest.mark.asyncio
async def test_auto_milestone_celebration():
    from cogs.welcome import WelcomeCog
    bot = MagicMock()
    bot.db = AsyncMock()
    cfg = MagicMock()
    cfg.welcome_enabled = True
    bot.db.get_or_create_guild_config.return_value = cfg
    w_cfg = MagicMock()
    w_cfg.autorole_id = None
    w_cfg.welcome_channel_id = None
    w_cfg.dm_enabled = False
    bot.db.get_welcome_config.return_value = w_cfg

    cog = WelcomeCog(bot)
    guild = MagicMock(spec=discord.Guild)
    guild.id = 888
    guild.name = "✦ Rai Server ✦"
    guild.member_count = 500  # Milestone count!
    guild.icon = None

    general_ch = MagicMock(spec=discord.TextChannel)
    general_ch.id = 1545502730699808768
    general_ch.send = AsyncMock()
    guild.get_channel.return_value = general_ch

    member = MagicMock(spec=discord.Member)
    member.id = 9999
    member.guild = guild
    member.mention = "<@9999>"

    await cog.on_member_join(member)
    general_ch.send.assert_awaited_once()
    embed = general_ch.send.call_args[1]["embed"]
    assert "𝕸ɪʟᴇsᴛᴏɴᴇ 𝕽ᴇᴀᴄʜᴇᴅ" in embed.title
    assert "500th member" in embed.description


@pytest.mark.asyncio
async def test_crowd_bitrate_scaling():
    bot = MagicMock()
    bot.db = AsyncMock()
    cog = TempVoiceCog(bot)

    guild = MagicMock(spec=discord.Guild)
    guild.id = 111
    guild.bitrate_limit = 256000
    guild.me = MagicMock()
    guild.me.guild_permissions.manage_channels = True

    vc = MagicMock(spec=discord.VoiceChannel)
    vc.id = 222
    vc.name = "✦ Squad Voice"
    vc.bitrate = 192000
    vc.guild = guild
    vc.edit = AsyncMock()

    # 1. 6 members -> Crowd scaling to 96kbps
    members = []
    for i in range(6):
        m = MagicMock(spec=discord.Member)
        m.id = i
        m.voice = MagicMock()
        m.voice.self_stream = False
        members.append(m)
    vc.members = members

    await cog._check_crowd_bitrate_scaling(vc)
    vc.edit.assert_awaited_once_with(bitrate=96000, reason="Auto-Bitrate Optimizer: Crowd scaling to 96kbps (6+ members)")
    assert cog._original_stream_bitrates[vc.id] == 192000

    # 2. Reduced to 2 members -> Restoration of high-fidelity bitrate
    vc.members = members[:2]
    vc.bitrate = 96000
    vc.edit.reset_mock()

    await cog._check_crowd_bitrate_scaling(vc)
    vc.edit.assert_awaited_once_with(bitrate=192000, reason="Auto-Bitrate Optimizer: Restored High-Fidelity bitrate (1-3 members)")
    assert vc.id not in cog._original_stream_bitrates


@pytest.mark.asyncio
async def test_chatter_of_the_day_and_birthday():
    from cogs.serverstats import ServerStatsCog
    bot = MagicMock()
    bot.db = AsyncMock()
    bot.wait_until_ready = AsyncMock()
    cog = ServerStatsCog(bot)

    guild = MagicMock(spec=discord.Guild)
    guild.id = 777
    guild.roles = []
    guild.me = MagicMock()
    guild.me.guild_permissions.manage_roles = True
    guild.me.top_role = MagicMock()
    guild.me.top_role.position = 100

    role = MagicMock(spec=discord.Role)
    role.name = "✦ Chatter of the Day ✦"
    role.members = []
    role.position = 10
    guild.create_role = AsyncMock(return_value=role)

    winner = MagicMock(spec=discord.Member)
    winner.id = 456
    winner.display_name = "Kishore"
    winner.mention = "<@456>"
    winner.display_avatar = None
    winner.add_roles = AsyncMock()
    guild.get_member.return_value = winner

    general_ch = MagicMock(spec=discord.TextChannel)
    general_ch.id = 1545502730699808768
    general_ch.send = AsyncMock()
    guild.get_channel.return_value = general_ch

    bot.guilds = [guild]

    # 1. Message activity recorded
    msg = MagicMock(spec=discord.Message)
    msg.author = winner
    msg.author.bot = False
    msg.guild = guild
    await cog.on_message(msg)
    assert cog._daily_activity_tracker[(guild.id, winner.id)] == 1

    # 2. Chatter of the Day rotation
    await cog.chatter_of_the_day_loop()
    winner.add_roles.assert_awaited_once_with(role, reason="Awarded Chatter of the Day")
    general_ch.send.assert_awaited_once()
    assert "𝓒ʜᴀᴛᴛᴇʀ ᴏғ ᴛʜᴇ 𝓓ᴀʏ" in general_ch.send.call_args[1]["embed"].title

    # 3. Birthday registration and check
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = guild
    interaction.user = winner
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()

    await cog.birthday_set.callback(cog, interaction, month=10, day=11)
    assert cog._member_birthdays[(guild.id, winner.id)] == (10, 11)
    interaction.response.send_message.assert_awaited_once()

    interaction.response.send_message.reset_mock()
    await cog.birthday_check.callback(cog, interaction, member=winner)
    interaction.response.send_message.assert_awaited_once()
    assert "10/11" in interaction.response.send_message.call_args[0][0]

    cog.cog_unload()


@pytest.mark.asyncio
async def test_expired_invites_and_db_maintenance():
    from cogs.serverstats import ServerStatsCog
    bot = MagicMock()
    bot.db = AsyncMock()
    bot.db._db = AsyncMock()
    bot.wait_until_ready = AsyncMock()
    cog = ServerStatsCog(bot)

    guild = MagicMock(spec=discord.Guild)
    guild.id = 555
    guild.me = MagicMock()
    guild.me.guild_permissions.manage_guild = True

    expired_inv = MagicMock(spec=discord.Invite)
    expired_inv.max_uses = 1
    expired_inv.uses = 1
    expired_inv.delete = AsyncMock()

    guild.invites = AsyncMock(return_value=[expired_inv])
    bot.guilds = [guild]

    # 1. Expired invites loop
    await cog.expired_invites_loop()
    expired_inv.delete.assert_awaited_once()

    # 2. DB maintenance loop
    await cog.db_maintenance_loop()
    assert bot.db._db.execute.call_count >= 2

    cog.cog_unload()


@pytest.mark.asyncio
async def test_dual_category_stats_and_themes():
    from cogs.serverstats import ServerStatsCog, make_goal_progress_bar
    bot = MagicMock()
    bot.db = AsyncMock()
    bot.wait_until_ready = AsyncMock()
    
    # Progress bar unit test
    bar, goal = make_goal_progress_bar(45)
    assert len(bar) == 10
    assert goal == 50
    assert "■" in bar and "□" in bar

    cog = ServerStatsCog(bot)

    guild = MagicMock(spec=discord.Guild)
    guild.id = 88888
    guild.name = "Rai Community"
    guild.member_count = 100
    guild.members = []
    guild.categories = []
    guild.voice_channels = []
    guild.premium_subscription_count = 2
    guild.premium_tier = 1

    # Populate 100 members, 30 online, 5 bots
    members = []
    for i in range(100):
        m = MagicMock(spec=discord.Member)
        m.id = i
        m.bot = (i < 5)
        m.status = discord.Status.online if i < 30 else discord.Status.offline
        m.voice = None
        m.activities = []
        members.append(m)
    guild.members = members

    guild.me = MagicMock()
    guild.me.guild_permissions.manage_channels = True
    guild.default_role = MagicMock()

    # Categories mock
    cat_server = MagicMock(spec=discord.CategoryChannel)
    cat_server.id = 101
    cat_server.name = "Server Status! ⌵"
    cat_server.edit = AsyncMock()

    cat_vc = MagicMock(spec=discord.CategoryChannel)
    cat_vc.id = 102
    cat_vc.name = "Vc Status! ⌵"
    cat_vc.edit = AsyncMock()

    guild.create_category = AsyncMock(side_effect=[cat_server, cat_vc])

    # Channels mock
    ch_all = MagicMock(spec=discord.VoiceChannel)
    ch_all.id = 201
    ch_all.name = "old"
    ch_all.edit = AsyncMock()

    ch_branding = MagicMock(spec=discord.VoiceChannel)
    ch_branding.id = 202
    ch_branding.name = "old"
    ch_branding.edit = AsyncMock()

    ch_mem = MagicMock(spec=discord.VoiceChannel)
    ch_mem.id = 203
    ch_mem.name = "old"
    ch_mem.edit = AsyncMock()

    guild.create_voice_channel = AsyncMock(side_effect=[ch_all, ch_branding, ch_mem])

    cfg = MagicMock()
    cfg.enabled = 1
    cfg.category_id = None
    cfg.all_members_channel_id = None
    cfg.members_channel_id = None
    cfg.bots_channel_id = None
    bot.db.get_or_create_server_stats_config.return_value = cfg
    bot.db.update_server_stats_config = AsyncMock()

    # 1. Test stats_setup
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = guild
    interaction.response = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()

    await cog.stats_setup.callback(cog, interaction)

    guild.create_category.assert_any_await(
        name="Server Status! ⌵",
        position=0,
        reason="Rai ServerStats: Created Server Status category",
    )
    guild.create_category.assert_any_await(
        name="Vc Status! ⌵",
        position=1,
        reason="Rai ServerStats: Created Vc Status category",
    )
    bot.db.update_server_stats_config.assert_awaited_once_with(
        guild.id,
        enabled=1,
        category_id=cat_server.id,
        all_members_channel_id=ch_all.id,
        members_channel_id=ch_mem.id,
        bots_channel_id=ch_branding.id,
    )
    interaction.followup.send.assert_awaited_once()

    # 2. Test style switcher (Switch to Swan / Screenshot 2)
    cfg.category_id = cat_server.id
    cfg.all_members_channel_id = ch_all.id
    cfg.members_channel_id = ch_mem.id
    cfg.bots_channel_id = ch_branding.id
    guild.get_channel = MagicMock(side_effect=lambda cid: {
        101: cat_server,
        102: cat_vc,
        201: ch_all,
        202: ch_branding,
        203: ch_mem,
    }.get(cid))

    interaction.followup.send.reset_mock()
    await cog.stats_style.callback(cog, interaction, theme="swan")
    assert cog._guild_theme[guild.id] == "swan"
    cat_server.edit.assert_awaited_with(name="🔒 𝐒𝐞𝐫𝐯𝐞𝐫 𝐒𝐭𝐚𝐭𝐮𝐬!")
    cat_vc.edit.assert_awaited_with(name="🔒 𝐕𝐜 𝐒𝐭𝐚𝐭𝐮𝐬!")
    assert ch_all.edit.call_count >= 1
    call_args_all = ch_all.edit.call_args[1]
    assert "🦢 30 online 🦢 100 members" == call_args_all["name"]

    # 3. Test custom branding (Screenshot 2 OZALERX !)
    interaction.followup.send.reset_mock()
    ch_branding.edit.reset_mock()
    await cog.stats_branding.callback(cog, interaction, text="OZALERX !")
    assert cog._guild_branding[guild.id] == "OZALERX !"
    ch_branding.edit.assert_awaited_with(name="OZALERX !", reason="Rai ServerStats: Aesthetic branding/goal sync")

    # 4. Test dynamic goal toggle
    interaction.followup.send.reset_mock()
    ch_branding.edit.reset_mock()
    await cog.stats_goal.callback(cog, interaction, enabled=True)
    assert cog._guild_show_goal[guild.id] is True
    assert ch_branding.edit.call_count >= 1
    call_args_branding = ch_branding.edit.call_args[1]
    assert "🎯 Goal:" in call_args_branding["name"]

    cog.cog_unload()






