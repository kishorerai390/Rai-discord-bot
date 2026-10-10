import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from cogs.temp_voice import TempVoiceCog
from database.models import DynamicRoom, TempVoiceConfig
from utils.dynamic_vc_control import BUILTIN_TEMPLATES, DynamicVCControlManager, normalize_channel_name


def test_builtin_templates_presets():
    """Verify that all gaming and editing capacity presets are configured."""
    assert "Solo" in BUILTIN_TEMPLATES
    assert BUILTIN_TEMPLATES["Solo"]["user_limit"] == 1
    assert "Duo" in BUILTIN_TEMPLATES
    assert BUILTIN_TEMPLATES["Duo"]["user_limit"] == 2
    assert "Trio" in BUILTIN_TEMPLATES
    assert BUILTIN_TEMPLATES["Trio"]["user_limit"] == 3
    assert "Squad" in BUILTIN_TEMPLATES
    assert BUILTIN_TEMPLATES["Squad"]["user_limit"] == 4
    assert "PC Editing" in BUILTIN_TEMPLATES
    assert BUILTIN_TEMPLATES["PC Editing"]["user_limit"] == 5
    assert "Mobile Editing" in BUILTIN_TEMPLATES
    assert BUILTIN_TEMPLATES["Mobile Editing"]["user_limit"] == 5
    assert "General Creative" in BUILTIN_TEMPLATES
    assert BUILTIN_TEMPLATES["General Creative"]["user_limit"] == 10
    assert "Editing Collab" in BUILTIN_TEMPLATES
    assert BUILTIN_TEMPLATES["Editing Collab"]["user_limit"] == 2
    assert "Private Editing" in BUILTIN_TEMPLATES
    assert BUILTIN_TEMPLATES["Private Editing"]["privacy"] == "owner_only"


@pytest.mark.asyncio
async def test_trigger_detection_gaming_and_editing():
    """Verify normalize_channel_name and trigger detection logic."""
    names = [
        ("🦢・Create Personal Gaming VC", "gaming_personal", False),
        ("🔒・Create Private Gaming VC", "gaming_private", True),
        ("🖥️・Create Personal Editing VC", "editing_personal", False),
        ("🔐・Create Private Editing VC", "editing_private", True),
    ]

    for raw, expected_mode, expected_private in names:
        norm = normalize_channel_name(raw)
        if "gaming" in norm and "private" in norm:
            mode = "gaming_private"
            is_priv = True
        elif "gaming" in norm and ("create" in norm or "personal" in norm or "vc" in norm):
            mode = "gaming_personal"
            is_priv = False
        elif "editing" in norm and "private" in norm:
            mode = "editing_private"
            is_priv = True
        elif "editing" in norm and ("create" in norm or "personal" in norm or "vc" in norm):
            mode = "editing_personal"
            is_priv = False
        else:
            mode = None
            is_priv = False

        assert mode == expected_mode
        assert is_priv == expected_private


@pytest.mark.asyncio
async def test_create_room_personal_gaming():
    bot = MagicMock()
    bot.db = AsyncMock()
    bot.db.get_temp_voice_config = AsyncMock(return_value=TempVoiceConfig(guild_id=123, enabled=True))
    bot.db.get_dynamic_room_by_owner = AsyncMock(return_value=None)
    bot.db.create_dynamic_room = AsyncMock()
    bot.db.update_dynamic_room = AsyncMock()

    cog = TempVoiceCog(bot)

    guild = MagicMock()
    guild.id = 123
    guild.default_role = MagicMock()

    category = MagicMock()
    guild.get_channel = MagicMock(return_value=category)

    created_vc = MagicMock(spec=discord.VoiceChannel)
    created_vc.id = 55555
    created_vc.name = "🎮・Tester's Room"
    created_vc.send = AsyncMock()
    guild.create_voice_channel = AsyncMock(return_value=created_vc)

    member = MagicMock()
    member.guild = guild
    member.id = 9999
    member.display_name = "Tester"
    member.mention = "<@9999>"
    member.voice = None
    member.send = AsyncMock()

    trigger_ch = MagicMock()
    trigger_ch.category = category

    with patch.object(DynamicVCControlManager, "create_room_panel", AsyncMock(return_value=MagicMock(id=888, channel=MagicMock(id=777)))):
        vc = await cog.create_room_for_member(
            member=member,
            is_private=False,
            trigger_channel=trigger_ch,
            mode="gaming_personal",
        )

    assert vc is not None
    # Verify create_voice_channel call arguments
    args, kwargs = guild.create_voice_channel.call_args
    assert "🎮・Tester's Room" in kwargs["name"]
    assert kwargs["user_limit"] == 4
    assert kwargs["category"] == category
    assert kwargs["overwrites"][guild.default_role].connect is True
    # Verify native text chat message was sent with view
    created_vc.send.assert_called_once()
    send_args, send_kwargs = created_vc.send.call_args
    assert "view" in send_kwargs
    assert send_kwargs["view"] is not None


@pytest.mark.asyncio
async def test_create_room_private_gaming():
    bot = MagicMock()
    bot.db = AsyncMock()
    bot.db.get_temp_voice_config = AsyncMock(return_value=TempVoiceConfig(guild_id=123, enabled=True))
    bot.db.get_dynamic_room_by_owner = AsyncMock(return_value=None)
    bot.db.create_dynamic_room = AsyncMock()
    bot.db.update_dynamic_room = AsyncMock()

    cog = TempVoiceCog(bot)

    guild = MagicMock()
    guild.id = 123
    guild.default_role = MagicMock()

    category = MagicMock()
    guild.get_channel = MagicMock(return_value=category)

    created_vc = MagicMock(spec=discord.VoiceChannel)
    created_vc.id = 66666
    created_vc.name = "🔒・Tester's Squad"
    created_vc.send = AsyncMock()
    guild.create_voice_channel = AsyncMock(return_value=created_vc)

    member = MagicMock()
    member.guild = guild
    member.id = 9999
    member.display_name = "Tester"
    member.mention = "<@9999>"
    member.voice = None
    member.send = AsyncMock()

    trigger_ch = MagicMock()
    trigger_ch.category = category

    with patch.object(DynamicVCControlManager, "create_room_panel", AsyncMock(return_value=MagicMock(id=888, channel=MagicMock(id=777)))):
        vc = await cog.create_room_for_member(
            member=member,
            is_private=True,
            trigger_channel=trigger_ch,
            mode="gaming_private",
        )

    assert vc is not None
    args, kwargs = guild.create_voice_channel.call_args
    assert "🔒・Tester's Squad" in kwargs["name"]
    assert kwargs["user_limit"] == 2
    # Verify private permissions: default_role view_channel=False, connect=False
    assert kwargs["overwrites"][guild.default_role].view_channel is False
    assert kwargs["overwrites"][guild.default_role].connect is False
    # Member permissions: view_channel=True, connect=True
    assert kwargs["overwrites"][member].view_channel is True
    assert kwargs["overwrites"][member].connect is True


@pytest.mark.asyncio
async def test_create_room_personal_editing():
    bot = MagicMock()
    bot.db = AsyncMock()
    bot.db.get_temp_voice_config = AsyncMock(return_value=TempVoiceConfig(guild_id=123, enabled=True))
    bot.db.get_dynamic_room_by_owner = AsyncMock(return_value=None)
    bot.db.create_dynamic_room = AsyncMock()
    bot.db.update_dynamic_room = AsyncMock()

    cog = TempVoiceCog(bot)

    guild = MagicMock()
    guild.id = 123
    guild.default_role = MagicMock()

    category = MagicMock()
    guild.get_channel = MagicMock(return_value=category)

    created_vc = MagicMock(spec=discord.VoiceChannel)
    created_vc.id = 77777
    created_vc.name = "🎨・Tester's Studio"
    created_vc.send = AsyncMock()
    guild.create_voice_channel = AsyncMock(return_value=created_vc)

    member = MagicMock()
    member.guild = guild
    member.id = 9999
    member.display_name = "Tester"
    member.mention = "<@9999>"
    member.voice = None
    member.send = AsyncMock()

    trigger_ch = MagicMock()
    trigger_ch.category = category

    with patch.object(DynamicVCControlManager, "create_room_panel", AsyncMock(return_value=MagicMock(id=888, channel=MagicMock(id=777)))):
        vc = await cog.create_room_for_member(
            member=member,
            is_private=False,
            trigger_channel=trigger_ch,
            mode="editing_personal",
        )

    assert vc is not None
    args, kwargs = guild.create_voice_channel.call_args
    assert "🎨・Tester's Studio" in kwargs["name"]
    assert kwargs["user_limit"] == 5
    assert kwargs["overwrites"][guild.default_role].connect is True


@pytest.mark.asyncio
async def test_create_room_private_editing():
    bot = MagicMock()
    bot.db = AsyncMock()
    bot.db.get_temp_voice_config = AsyncMock(return_value=TempVoiceConfig(guild_id=123, enabled=True))
    bot.db.get_dynamic_room_by_owner = AsyncMock(return_value=None)
    bot.db.create_dynamic_room = AsyncMock()
    bot.db.update_dynamic_room = AsyncMock()

    cog = TempVoiceCog(bot)

    guild = MagicMock()
    guild.id = 123
    guild.default_role = MagicMock()

    category = MagicMock()
    guild.get_channel = MagicMock(return_value=category)

    created_vc = MagicMock(spec=discord.VoiceChannel)
    created_vc.id = 88888
    created_vc.name = "🔐・Tester's Suite"
    created_vc.send = AsyncMock()
    guild.create_voice_channel = AsyncMock(return_value=created_vc)

    member = MagicMock()
    member.guild = guild
    member.id = 9999
    member.display_name = "Tester"
    member.mention = "<@9999>"
    member.voice = None
    member.send = AsyncMock()

    trigger_ch = MagicMock()
    trigger_ch.category = category

    with patch.object(DynamicVCControlManager, "create_room_panel", AsyncMock(return_value=MagicMock(id=888, channel=MagicMock(id=777)))):
        vc = await cog.create_room_for_member(
            member=member,
            is_private=True,
            trigger_channel=trigger_ch,
            mode="editing_private",
        )

    assert vc is not None
    args, kwargs = guild.create_voice_channel.call_args
    assert "🔐・Tester's Suite" in kwargs["name"]
    assert kwargs["user_limit"] == 2
    assert kwargs["overwrites"][guild.default_role].view_channel is False
    assert kwargs["overwrites"][guild.default_role].connect is False
    assert kwargs["overwrites"][member].view_channel is True
    assert kwargs["overwrites"][member].connect is True
