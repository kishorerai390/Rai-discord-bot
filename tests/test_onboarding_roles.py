import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from utils.role_manager import OnboardingRoleView, ROLE_DEFINITIONS


def test_interest_roles_definitions():
    """Verify Gamer, Music Lover, and Editor exist and are self-assignable."""
    assert "gamer" in ROLE_DEFINITIONS
    assert ROLE_DEFINITIONS["gamer"].get("is_self_assignable") is True

    assert "music_lover" in ROLE_DEFINITIONS
    assert ROLE_DEFINITIONS["music_lover"].get("is_self_assignable") is True

    assert "editor" in ROLE_DEFINITIONS
    assert ROLE_DEFINITIONS["editor"].get("is_self_assignable") is True

    # Privileged roles MUST NOT be self-assignable
    assert ROLE_DEFINITIONS["server_owner"].get("is_self_assignable") is not True
    assert ROLE_DEFINITIONS["admin"].get("is_self_assignable") is not True
    assert ROLE_DEFINITIONS["moderator"].get("is_self_assignable") is not True
    assert ROLE_DEFINITIONS["bot"].get("is_self_assignable") is not True


def test_onboarding_role_view_components():
    """Verify OnboardingRoleView has 3 buttons with persistent custom_ids."""
    view = OnboardingRoleView()
    assert len(view.children) == 3

    custom_ids = [child.custom_id for child in view.children]
    assert "rai_role:toggle:gamer" in custom_ids
    assert "rai_role:toggle:music_lover" in custom_ids
    assert "rai_role:toggle:editor" in custom_ids


@pytest.mark.asyncio
async def test_onboarding_toggle_add_role():
    """Verify toggling a role on a user who does not have it adds the role."""
    view = OnboardingRoleView()

    guild = MagicMock(spec=discord.Guild)
    guild.id = 123
    guild.me = MagicMock()
    guild.me.guild_permissions.manage_roles = True

    bot_top_role = MagicMock(spec=discord.Role)
    bot_top_role.position = 50
    guild.me.top_role = bot_top_role

    gamer_role = MagicMock(spec=discord.Role)
    gamer_role.name = "🎮 Gamer"
    gamer_role.position = 20
    gamer_role.__ge__ = lambda s, o: gamer_role.position >= o.position
    guild.roles = [gamer_role]

    member = MagicMock(spec=discord.Member)
    member.roles = []
    member.add_roles = AsyncMock()
    member.remove_roles = AsyncMock()

    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = guild
    interaction.user = member
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()

    await view._toggle_role(interaction, "gamer")

    member.add_roles.assert_called_once_with(gamer_role, reason="Raivora Onboarding: Self-assigned interest role")
    member.remove_roles.assert_not_called()
    interaction.response.send_message.assert_called_once()
    msg = interaction.response.send_message.call_args[0][0]
    assert "Added" in msg


@pytest.mark.asyncio
async def test_onboarding_toggle_remove_role():
    """Verify toggling a role on a user who already has it removes the role."""
    view = OnboardingRoleView()

    guild = MagicMock(spec=discord.Guild)
    guild.id = 123
    guild.me = MagicMock()
    guild.me.guild_permissions.manage_roles = True

    bot_top_role = MagicMock(spec=discord.Role)
    bot_top_role.position = 50
    guild.me.top_role = bot_top_role

    gamer_role = MagicMock(spec=discord.Role)
    gamer_role.name = "🎮 Gamer"
    gamer_role.position = 20
    gamer_role.__ge__ = lambda s, o: gamer_role.position >= o.position
    guild.roles = [gamer_role]

    member = MagicMock(spec=discord.Member)
    member.roles = [gamer_role]
    member.add_roles = AsyncMock()
    member.remove_roles = AsyncMock()

    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = guild
    interaction.user = member
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()

    await view._toggle_role(interaction, "gamer")

    member.remove_roles.assert_called_once_with(gamer_role, reason="Raivora Onboarding: Self-removed interest role")
    member.add_roles.assert_not_called()
    interaction.response.send_message.assert_called_once()
    msg = interaction.response.send_message.call_args[0][0]
    assert "Removed" in msg
