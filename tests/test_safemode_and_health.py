import asyncio
import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from cogs.security import SecurityCog
from cogs.server_setup import ServerSetupCog
from database.models import SecurityIncident, SecurityState
from services.music_gateway import MusicBotStatus, MusicStatusInfo


@pytest.mark.asyncio
async def test_security_safemode_enable_and_disable():
    bot = MagicMock()
    bot.db = AsyncMock()
    bot.db.set_emergency_stop = AsyncMock()
    bot.db.get_security_state = AsyncMock(return_value=SecurityState(guild_id=123, emergency_stop=True))

    cog = SecurityCog(bot)
    cog._send_private_security_alert = AsyncMock()

    guild = MagicMock()
    guild.id = 123
    interaction = MagicMock()
    interaction.guild = guild
    interaction.user = MagicMock()
    interaction.user.id = 999
    interaction.user.mention = "<@999>"
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()

    # Enable Safe Mode
    choice_enable = MagicMock()
    choice_enable.value = "enable"
    await cog.security_safemode.callback(cog, interaction, action=choice_enable)
    bot.db.set_emergency_stop.assert_awaited_with(123, True, 999)
    cog._send_private_security_alert.assert_awaited_once()

    # Disable Safe Mode
    choice_disable = MagicMock()
    choice_disable.value = "disable"
    await cog.security_safemode.callback(cog, interaction, action=choice_disable)
    bot.db.set_emergency_stop.assert_awaited_with(123, False, 999)


@pytest.mark.asyncio
async def test_security_incident_timeline():
    bot = MagicMock()
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    mock_inc = SecurityIncident(
        event_id="TEST-INC-123",
        guild_id=123,
        timestamp=now_iso,
        event_type="CHANNEL_DELETE",
        executor_id=888,
        executor_name="RaidBot#0001",
        target_id=777,
        target_name="#chat",
        action="channel_delete",
        detected_count=5,
        threshold=3,
        audit_log_id=123456,
        reason="Rapid mass deletion",
        automated_action="Account Quarantined",
        result="Success",
        severity="high",
        audit_verified=True,
    )
    bot.db = AsyncMock()
    bot.db.get_security_incident = AsyncMock(return_value=mock_inc)

    cog = SecurityCog(bot)

    interaction = MagicMock()
    interaction.guild = MagicMock(id=123)
    interaction.response = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()

    await cog.security_incident_cmd.callback(cog, interaction, incident_id="TEST-INC-123")
    interaction.followup.send.assert_awaited_once()
    sent_embed = interaction.followup.send.call_args[1]["embed"]
    assert "TEST-INC-123" in sent_embed.title
    assert "CHANNEL_DELETE" in sent_embed.description
    assert "RaidBot#0001" in sent_embed.description
    assert "Account Quarantined" in sent_embed.description


@pytest.mark.asyncio
async def test_server_health_dashboard():
    bot = MagicMock()
    bot.latency = 0.042
    bot._start_time = datetime.datetime.now(datetime.timezone.utc).timestamp() - 7200
    bot.db = AsyncMock()
    bot.db.check_integrity = AsyncMock(return_value=(True, []))
    bot.db.get_all_dynamic_rooms = AsyncMock(return_value=[])
    bot.db.get_security_incidents = AsyncMock(return_value=[])

    cog = ServerSetupCog(bot)

    guild = MagicMock()
    guild.name = "Test Community"
    guild.id = 123456
    guild.me = MagicMock()
    guild.me.guild_permissions = discord.Permissions(
        manage_channels=True,
        manage_roles=True,
        view_audit_log=True,
        move_members=True,
    )

    interaction = MagicMock()
    interaction.guild = guild
    interaction.user = MagicMock()
    interaction.user.guild_permissions = discord.Permissions(administrator=True)
    interaction.response = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()

    mock_music_status = MusicStatusInfo(
        status=MusicBotStatus.CONNECTED,
        bot_name="Neko Songs",
        bot_id=1556676516274905218,
        version="2.0.0",
        active_sessions=1,
        playing_count=1,
    )

    with patch("services.music_gateway.MusicGateway.get_status", AsyncMock(return_value=mock_music_status)):
        await cog.server_health.callback(cog, interaction)

    interaction.followup.send.assert_awaited_once()
    embed = interaction.followup.send.call_args[1]["embed"]
    assert "SERVER HEALTH" in embed.title
    assert "Gateway Latency" in embed.description
    assert "Database Health" in embed.description
    assert "Dynamic Voice Subsystem" in embed.description
