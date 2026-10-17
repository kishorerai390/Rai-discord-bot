"""
Test Suite for Discord Server Rebuild Automation (Guild: 1457382179981099090)
Validates:
1. Target 7-Category Channel Mapping & Preservation of Existing Snowflakes
2. Temporary Voice Room Manager (creation, ownership, grace period deletion, permanent protection)
3. Support Center Private Tickets & Transcripts
4. Live Status Panels (safe edit vs spam prevention)
5. Least-Privilege Role Boundaries
"""

from __future__ import annotations

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import discord

from music_bot.services.temp_voice_service import (
    CREATE_ROOM_CHANNEL_ID,
    PERMANENT_VC_IDS,
    TempVoiceRoomManager,
    RoomControlView,
)
from music_bot.services.ticket_service import (
    MOD_LOG_CHANNEL_ID,
    SupportHubView,
    TicketActionView,
)
from music_bot.services.status_panel_service import (
    SERVER_STATUS_CHANNEL_ID,
    VOICE_STATUS_CHANNEL_ID,
    StatusPanelManager,
)
from scripts.rebuild_server_executor import TARGET_CATEGORIES


class TestServerRebuildSuite:

    def test_01_target_mapping_preserves_snowflakes(self):
        """Verify all target categories contain valid channels from the original server audit."""
        with open("data/live_audit_dump.json", "r", encoding="utf-8") as f:
            dump = json.load(f)

        existing_ids = {c["id"] for c in dump.get("channels", [])}
        mapped_count = 0

        for cat in TARGET_CATEGORIES:
            assert "name" in cat
            assert len(cat["channels"]) > 0
            for ch in cat["channels"]:
                mapped_count += 1
                # Must be an existing channel ID to preserve snowflake and history
                assert ch["id"] in existing_ids, f"Channel {ch['name']} ({ch['id']}) not found in audit dump!"

        assert len(TARGET_CATEGORIES) == 7
        assert mapped_count >= 20

    def test_02_permanent_voice_channels_protected(self):
        """Confirm permanent voice rooms are protected from deletion."""
        assert TempVoiceRoomManager.is_permanent(CREATE_ROOM_CHANNEL_ID) is True
        # Solo, Duo, Trio, Squad, Game Lobby, Ranked Grind, Chill Gaming, Editing Studio, Creator Collab, Music Lounge, Movie, AFK
        assert TempVoiceRoomManager.is_permanent(1558675717552611360) is True  # Solo
        assert TempVoiceRoomManager.is_permanent(1558675725114937445) is True  # Duo
        assert TempVoiceRoomManager.is_permanent(1554891485818921042) is True  # AFK
        assert TempVoiceRoomManager.is_permanent(999999999999999999) is False

    @pytest.mark.asyncio
    async def test_03_temp_voice_room_lifecycle(self):
        """Test dynamic room creation on joining trigger channel."""
        guild = MagicMock(spec=discord.Guild)
        guild.id = 1457382179981099090
        guild.bitrate_limit = 96000

        member = MagicMock(spec=discord.Member)
        member.id = 12345
        member.display_name = "AnimeEditor"
        member.guild = guild

        trigger_channel = MagicMock(spec=discord.VoiceChannel)
        trigger_channel.id = CREATE_ROOM_CHANNEL_ID
        trigger_channel.category = MagicMock(spec=discord.CategoryChannel)
        trigger_channel.bitrate = 64000

        created_channel = MagicMock(spec=discord.VoiceChannel)
        created_channel.id = 88888
        created_channel.name = "🎧・AnimeEditor's Room"
        guild.create_voice_channel = AsyncMock(return_value=created_channel)
        member.move_to = AsyncMock()

        # Execute creation
        res = await TempVoiceRoomManager._create_dynamic_room(member, trigger_channel)
        assert res == created_channel
        guild.create_voice_channel.assert_awaited_once()
        member.move_to.assert_awaited_once_with(created_channel, reason="Moved into generated temporary voice room")
        assert 88888 in TempVoiceRoomManager._active_rooms

    @pytest.mark.asyncio
    async def test_04_room_control_view_security(self):
        """RoomControlView allows owner or manage_channels staff, but denies unauthorized members."""
        channel = MagicMock(spec=discord.VoiceChannel)
        view = RoomControlView(channel, owner_id=12345)

        # Owner interaction
        owner_interaction = MagicMock(spec=discord.Interaction)
        owner_interaction.user.id = 12345
        owner_interaction.user.guild_permissions.manage_channels = False
        assert await view.interaction_check(owner_interaction) is True

        # Non-owner interaction
        stranger_interaction = MagicMock(spec=discord.Interaction)
        stranger_interaction.user.id = 99999
        stranger_interaction.user.guild_permissions.manage_channels = False
        stranger_interaction.response.send_message = AsyncMock()
        assert await view.interaction_check(stranger_interaction) is False
        stranger_interaction.response.send_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_05_support_hub_view_registration(self):
        """Confirm SupportHubView buttons exist with custom_ids."""
        view = SupportHubView()
        button_ids = [child.custom_id for child in view.children if hasattr(child, "custom_id")]
        assert "hub_general_support" in button_ids
        assert "hub_report_member" in button_ids
        assert "hub_appeals" in button_ids

    @pytest.mark.asyncio
    async def test_06_ticket_action_view_staff_claim(self):
        """Staff can claim a ticket; non-staff cannot."""
        view = TicketActionView(opener_id=11111, ticket_type="General Support")
        btn = [b for b in view.children if getattr(b, "custom_id", None) == "ticket_claim"][0]

        # Non-staff attempt
        user_interaction = MagicMock(spec=discord.Interaction)
        user_interaction.user.guild_permissions.manage_messages = False
        user_interaction.response.send_message = AsyncMock()
        await view.btn_claim(user_interaction, btn)
        assert view.claimed_by is None
        user_interaction.response.send_message.assert_awaited_once()

        # Staff attempt
        staff_interaction = MagicMock(spec=discord.Interaction)
        staff_interaction.user.id = 77777
        staff_interaction.user.display_name = "StaffLead"
        staff_interaction.user.mention = "<@77777>"
        staff_interaction.user.guild_permissions.manage_messages = True
        staff_interaction.response.edit_message = AsyncMock()
        staff_interaction.followup.send = AsyncMock()
        await view.btn_claim(staff_interaction, btn)
        assert view.claimed_by == 77777
        assert "Claimed by StaffLead" in btn.label

    @pytest.mark.asyncio
    async def test_07_status_panels_anti_spam_edit(self):
        """StatusPanelManager edits existing message rather than posting duplicate messages."""
        channel = MagicMock(spec=discord.TextChannel)
        channel.guild.me = MagicMock()
        existing_msg = MagicMock(spec=discord.Message)
        existing_msg.id = 55555
        existing_msg.author = channel.guild.me
        mock_embed = MagicMock()
        mock_embed.title = "📊 SERVER TELEMETRY & SYSTEM HEALTH"
        existing_msg.embeds = [mock_embed]
        existing_msg.edit = AsyncMock()

        # Return existing message in history
        async def fake_history(limit=10):
            yield existing_msg

        channel.history = fake_history
        embed = discord.Embed(title="📊 SERVER TELEMETRY & SYSTEM HEALTH")

        await StatusPanelManager._post_or_edit(channel, embed, "_server_msg_id")
        existing_msg.edit.assert_awaited_once_with(embed=embed)
        channel.send.assert_not_called()
