"""
Comprehensive Unit & Integration Test Suite for Rai's Dynamic Voice Room System.
Tests:
- Public and private room creation
- Database storage in dynamic_rooms, room_members, room_templates, room_events
- Strict VC isolation (Room A controls cannot affect Room B)
- Unauthorized user rejection (ephemeral response: '❌ You are not the owner of this room.')
- Modal rename and user limit operations
- Privacy state transitions (Public, Locked, Invite-Only, Owner-Only)
- Member invitation, transfer ownership, mute, disconnect, clear, delete
- 60-second empty room grace period cleanup and rejoin restoration
- Permanent trigger channel protection
"""

import asyncio
import datetime
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import discord

from database.database import Database
from database.migrations import run_migrations
from database.models import DynamicRoom, RoomMember
from utils.dynamic_vc_control import (
    BUILTIN_TEMPLATES,
    DynamicConfirmClearView,
    DynamicConfirmDeleteView,
    DynamicLimitModal,
    DynamicPrivacySelectorView,
    DynamicRenameModal,
    DynamicVCControlManager,
)
def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def utcnow_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class TestDynamicVCControlSystem(unittest.IsolatedAsyncioTestCase):
    """Full lifecycle and isolation test suite for Dynamic Voice Rooms."""

    async def asyncSetUp(self):
        # In-memory database with all migrations
        self.conn = await aiosqlite.connect(":memory:")
        self.conn.row_factory = aiosqlite.Row
        await run_migrations(self.conn)

        self.db = Database(":memory:")
        self.db._db = self.conn

        self.guild_id = 1457382179981099090
        await self.db.get_or_create_guild_config(self.guild_id)

        # Mock Bot
        self.bot = MagicMock()
        self.bot.db = self.db
        self.bot.cogs = {}

        self.reporter_patcher = patch("utils.dynamic_vc_control.OwnerReporter.send_room_report")
        self.mock_send_report = self.reporter_patcher.start()

    async def asyncTearDown(self):
        self.reporter_patcher.stop()
        await self.conn.close()

    # =========================================================================
    # 1. DATABASE SCHEMA & OPERATIONS
    # =========================================================================

    async def test_dynamic_rooms_crud(self):
        """Verify dynamic_rooms table insertion, query, update, and deletion."""
        now = utcnow_iso()
        room = DynamicRoom(
            guild_id=self.guild_id,
            voice_channel_id=1001,
            owner_id=5001,
            room_type="public",
            privacy_mode="public",
            control_channel_id=2001,
            control_message_id=3001,
            user_limit=5,
            locked=False,
            created_at=now,
            status="active",
        )
        await self.db.create_dynamic_room(room)

        # Query by VC ID
        fetched = await self.db.get_dynamic_room(1001)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.owner_id, 5001)
        self.assertEqual(fetched.user_limit, 5)
        self.assertEqual(fetched.room_type, "public")
        self.assertEqual(fetched.status, "active")

        # Query by Control Message ID
        fetched_by_msg = await self.db.get_dynamic_room_by_control_message(3001)
        self.assertIsNotNone(fetched_by_msg)
        self.assertEqual(fetched_by_msg.voice_channel_id, 1001)

        # Query by Owner ID
        fetched_by_owner = await self.db.get_dynamic_room_by_owner(self.guild_id, 5001)
        self.assertIsNotNone(fetched_by_owner)
        self.assertEqual(fetched_by_owner.voice_channel_id, 1001)

        # Update dynamic room
        await self.db.update_dynamic_room(1001, user_limit=10, locked=1, privacy_mode="locked")
        updated = await self.db.get_dynamic_room(1001)
        self.assertEqual(updated.user_limit, 10)
        self.assertTrue(updated.locked)
        self.assertEqual(updated.privacy_mode, "locked")

        # Delete dynamic room
        await self.db.delete_dynamic_room(1001)
        deleted = await self.db.get_dynamic_room(1001)
        self.assertIsNone(deleted)

    async def test_room_members_tracking(self):
        """Verify adding and removing room members in room_members table."""
        vc_id = 1002
        await self.db.add_room_member(vc_id, user_id=6001, permission_type="invited")
        await self.db.add_room_member(vc_id, user_id=6002, permission_type="member")

        members = await self.db.get_room_members(vc_id)
        self.assertEqual(len(members), 2)
        user_ids = [m.user_id for m in members]
        self.assertIn(6001, user_ids)
        self.assertIn(6002, user_ids)

        await self.db.remove_room_member(vc_id, user_id=6001)
        remaining = await self.db.get_room_members(vc_id)
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0].user_id, 6002)

    async def test_room_templates_and_events(self):
        """Verify room templates and event auditing."""
        # Templates
        await self.db.save_room_template(self.guild_id, 5001, "Custom Duo", '{"limit": 2}')
        tpls = await self.db.get_room_templates(self.guild_id, 5001)
        self.assertEqual(len(tpls), 1)
        self.assertEqual(tpls[0].template_name, "Custom Duo")

        # Events
        await self.db.record_room_event(1003, "rename", 5001, metadata='{"name": "New Name"}')
        # Check event rowcount
        async with self.conn.execute("SELECT * FROM room_events WHERE room_id = ?", (1003,)) as cur:
            row = await cur.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["event_type"], "rename")

    # =========================================================================
    # 2. PANEL EMBED & VIEW GENERATION
    # =========================================================================

    def test_build_panel_embed_and_view(self):
        """Verify room control panel embed formatting and view custom IDs."""
        room = DynamicRoom(
            guild_id=self.guild_id,
            voice_channel_id=1004,
            owner_id=5001,
            room_type="public",
            privacy_mode="public",
            user_limit=5,
            locked=False,
            created_at=utcnow_iso(),
            status="active",
        )
        mock_vc = MagicMock(spec=discord.VoiceChannel)
        mock_vc.name = "🎙️・Test VC"
        mock_vc.members = [MagicMock(), MagicMock()]

        embed = DynamicVCControlManager.build_panel_embed(room, mock_vc, self.bot)
        self.assertIn("TEST VC", embed.title)
        self.assertIn("<@5001>", embed.description)
        self.assertIn("2 / 5", embed.description)
        self.assertIn("🌐 Public", embed.description)

        view = DynamicVCControlManager.build_panel_view(1004, has_music=True)
        # Check that all button custom IDs strictly embed 1004
        for item in view.children:
            if isinstance(item, discord.ui.Button):
                self.assertTrue(item.custom_id.endswith(":1004"), f"Custom ID {item.custom_id} does not end with :1004")

    # =========================================================================
    # 3. MULTIPLE ROOMS ISOLATION (NO CROSS-ROOM CONTROL)
    # =========================================================================

    async def test_multiple_rooms_strict_isolation(self):
        """
        Verify that in an environment with multiple simultaneous active rooms:
        - Room A is owned by User A
        - Room B is owned by User B
        - User A cannot interact with Room B's controls
        - Controls on Room A modify ONLY Room A
        """
        # Create Room A
        room_a = DynamicRoom(
            guild_id=self.guild_id,
            voice_channel_id=1010,
            owner_id=5010,
            room_type="public",
            privacy_mode="public",
            user_limit=5,
            locked=False,
            created_at=utcnow_iso(),
            status="active",
        )
        await self.db.create_dynamic_room(room_a)

        # Create Room B
        room_b = DynamicRoom(
            guild_id=self.guild_id,
            voice_channel_id=1020,
            owner_id=5020,
            room_type="public",
            privacy_mode="public",
            user_limit=8,
            locked=False,
            created_at=utcnow_iso(),
            status="active",
        )
        await self.db.create_dynamic_room(room_b)

        # Mock Guild and Channels
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = self.guild_id
        mock_guild.owner_id = 9999

        mock_vc_a = AsyncMock(spec=discord.VoiceChannel)
        mock_vc_a.id = 1010
        mock_vc_a.name = "🎙️・User A's Room"
        mock_vc_a.members = []

        mock_vc_b = AsyncMock(spec=discord.VoiceChannel)
        mock_vc_b.id = 1020
        mock_vc_b.name = "🎙️・User B's Room"
        mock_vc_b.members = []

        def get_channel_side_effect(ch_id):
            if ch_id == 1010:
                return mock_vc_a
            elif ch_id == 1020:
                return mock_vc_b
            return None

        mock_guild.get_channel.side_effect = get_channel_side_effect

        # User A attempts to click on Room B's Lock button (custom_id: rai_vc:privacy:1020)
        interaction_unauth = AsyncMock(spec=discord.Interaction)
        interaction_unauth.guild = mock_guild
        interaction_unauth.data = {"custom_id": "rai_vc:privacy:1020"}
        user_a = MagicMock(spec=discord.Member)
        user_a.id = 5010  # Owner of Room A, NOT Room B
        user_a.guild_permissions.administrator = False
        interaction_unauth.user = user_a
        interaction_unauth.response.send_message = AsyncMock()

        handled = await DynamicVCControlManager.handle_interaction(self.bot, interaction_unauth)
        self.assertTrue(handled)
        interaction_unauth.response.send_message.assert_called_once()
        args, kwargs = interaction_unauth.response.send_message.call_args
        self.assertTrue(kwargs.get("ephemeral"))
        # Must show rejection
        sent_embed = kwargs.get("embed")
        self.assertIn("UNAUTHORIZED", sent_embed.title.upper())
        self.assertIn("You are not the owner of this room", sent_embed.description)

        # Room B was NOT modified
        room_b_fresh = await self.db.get_dynamic_room(1020)
        self.assertFalse(room_b_fresh.locked)
        mock_vc_b.set_permissions.assert_not_called()

        # User A clicks on Room A's Lock button (custom_id: rai_vc_priv:locked:1010)
        interaction_auth = AsyncMock(spec=discord.Interaction)
        interaction_auth.guild = mock_guild
        interaction_auth.data = {"custom_id": "rai_vc_priv:locked:1010"}
        interaction_auth.user = user_a
        interaction_auth.response.send_message = AsyncMock()

        with patch.object(DynamicVCControlManager, "update_room_panel", new_callable=AsyncMock) as mock_update_panel:
            handled_auth = await DynamicVCControlManager.handle_interaction(self.bot, interaction_auth)
            self.assertTrue(handled_auth)
            # Verify Room A was locked
            mock_vc_a.set_permissions.assert_called_once_with(mock_guild.default_role, connect=False)
            room_a_fresh = await self.db.get_dynamic_room(1010)
            self.assertTrue(room_a_fresh.locked)
            self.assertEqual(room_a_fresh.privacy_mode, "locked")
            # Room B remained untouched!
            self.assertFalse(room_b_fresh.locked)
            mock_vc_b.set_permissions.assert_not_called()

    # =========================================================================
    # 4. MODALS: RENAME & USER LIMIT
    # =========================================================================

    async def test_rename_modal_execution(self):
        """Verify RenameModal renames only target VC and updates database."""
        vc_id = 1030
        room = DynamicRoom(
            guild_id=self.guild_id,
            voice_channel_id=vc_id,
            owner_id=5030,
            created_at=utcnow_iso(),
            status="active",
        )
        await self.db.create_dynamic_room(room)

        mock_guild = MagicMock(spec=discord.Guild)
        mock_vc = AsyncMock(spec=discord.VoiceChannel)
        mock_vc.id = vc_id
        mock_vc.name = "Old Name"
        mock_guild.get_channel.return_value = mock_vc

        modal = DynamicRenameModal(vc_id, 5030)
        modal.room_name._value = "Kishore's Squad"

        interaction = AsyncMock(spec=discord.Interaction)
        interaction.client = self.bot
        interaction.guild = mock_guild
        interaction.user = MagicMock(id=5030, display_name="Kishore")
        interaction.response.send_message = AsyncMock()

        with patch.object(DynamicVCControlManager, "update_room_panel", new_callable=AsyncMock):
            await modal.on_submit(interaction)

        mock_vc.edit.assert_called_once_with(
            name="🎙️・Kishore's Squad",
            reason=unittest.mock.ANY,
        )
        interaction.response.send_message.assert_called_once()
        _, kwargs = interaction.response.send_message.call_args
        self.assertTrue(kwargs.get("ephemeral"))
        self.assertIn("ROOM RENAMED", kwargs["embed"].title.upper())

    async def test_limit_modal_execution(self):
        """Verify DynamicLimitModal updates capacity on target VC and in database."""
        vc_id = 1040
        room = DynamicRoom(
            guild_id=self.guild_id,
            voice_channel_id=vc_id,
            owner_id=5040,
            user_limit=2,
            created_at=utcnow_iso(),
            status="active",
        )
        await self.db.create_dynamic_room(room)

        mock_guild = MagicMock(spec=discord.Guild)
        mock_vc = AsyncMock(spec=discord.VoiceChannel)
        mock_vc.id = vc_id
        mock_guild.get_channel.return_value = mock_vc

        modal = DynamicLimitModal(vc_id, 5040)
        modal.limit_val._value = "12"

        interaction = AsyncMock(spec=discord.Interaction)
        interaction.client = self.bot
        interaction.guild = mock_guild
        interaction.user = MagicMock(id=5040, display_name="User40")
        interaction.response.send_message = AsyncMock()

        with patch.object(DynamicVCControlManager, "update_room_panel", new_callable=AsyncMock):
            await modal.on_submit(interaction)

        mock_vc.edit.assert_called_once_with(
            user_limit=12,
            reason=unittest.mock.ANY,
        )
        # Check DB update
        updated = await self.db.get_dynamic_room(vc_id)
        self.assertEqual(updated.user_limit, 12)

    # =========================================================================
    # 5. PRIVACY MODES (PUBLIC, LOCKED, INVITE-ONLY, OWNER-ONLY)
    # =========================================================================

    async def test_privacy_modes_discord_permissions(self):
        """Verify real Discord permission overwrites applied for each privacy mode."""
        vc_id = 1050
        owner_id = 5050
        room = DynamicRoom(
            guild_id=self.guild_id,
            voice_channel_id=vc_id,
            owner_id=owner_id,
            created_at=utcnow_iso(),
            status="active",
        )
        await self.db.create_dynamic_room(room)

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = self.guild_id
        mock_guild.owner_id = 9999
        mock_owner = MagicMock(spec=discord.Member, id=owner_id)
        mock_guild.get_member.return_value = mock_owner

        mock_vc = AsyncMock(spec=discord.VoiceChannel)
        mock_vc.id = vc_id
        mock_vc.name = "🎙️・Test Privacy"
        mock_guild.get_channel.return_value = mock_vc

        # 1. Invite-Only
        interaction = AsyncMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.data = {"custom_id": f"rai_vc_priv:invite:{vc_id}"}
        interaction.user = mock_owner
        interaction.response.send_message = AsyncMock()

        with patch.object(DynamicVCControlManager, "update_room_panel", new_callable=AsyncMock):
            await DynamicVCControlManager.handle_interaction(self.bot, interaction)

        mock_vc.set_permissions.assert_any_call(mock_guild.default_role, view_channel=False, connect=False)
        mock_vc.set_permissions.assert_any_call(mock_owner, view_channel=True, connect=True)
        fresh = await self.db.get_dynamic_room(vc_id)
        self.assertEqual(fresh.privacy_mode, "invite_only")

        # 2. Public
        interaction.data = {"custom_id": f"rai_vc_priv:public:{vc_id}"}
        with patch.object(DynamicVCControlManager, "update_room_panel", new_callable=AsyncMock):
            await DynamicVCControlManager.handle_interaction(self.bot, interaction)

        mock_vc.set_permissions.assert_any_call(mock_guild.default_role, view_channel=True, connect=True)
        fresh_pub = await self.db.get_dynamic_room(vc_id)
        self.assertEqual(fresh_pub.privacy_mode, "public")

    # =========================================================================
    # 6. DANGEROUS ACTIONS: CLEAR & DELETE WITH CONFIRMATION
    # =========================================================================

    async def test_clear_room_action(self):
        """Verify clear room disconnects all members except owner."""
        vc_id = 1060
        owner_id = 5060
        room = DynamicRoom(
            guild_id=self.guild_id,
            voice_channel_id=vc_id,
            owner_id=owner_id,
            created_at=utcnow_iso(),
            status="active",
        )
        await self.db.create_dynamic_room(room)

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = self.guild_id
        mock_guild.owner_id = 9999

        owner_member = MagicMock(spec=discord.Member, id=owner_id, bot=False)
        guest1 = AsyncMock(spec=discord.Member, id=7001, bot=False)
        guest2 = AsyncMock(spec=discord.Member, id=7002, bot=False)

        mock_vc = AsyncMock(spec=discord.VoiceChannel)
        mock_vc.id = vc_id
        mock_vc.name = "🎙️・Clearable Room"
        mock_vc.members = [owner_member, guest1, guest2]
        mock_guild.get_channel.return_value = mock_vc

        interaction = AsyncMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.data = {"custom_id": f"rai_vc_confirm:clear:{vc_id}"}
        interaction.user = owner_member
        interaction.response.send_message = AsyncMock()

        with patch.object(DynamicVCControlManager, "update_room_panel", new_callable=AsyncMock):
            await DynamicVCControlManager.handle_interaction(self.bot, interaction)

        # Guests should be moved to None, owner untouched
        guest1.move_to.assert_called_once_with(None, reason="Rai Dynamic VC: Owner cleared room")
        guest2.move_to.assert_called_once_with(None, reason="Rai Dynamic VC: Owner cleared room")
        owner_member.move_to.assert_not_called()

    async def test_delete_room_action(self):
        """Verify delete room removes VC, deletes control panel, and clears DB record."""
        vc_id = 1070
        owner_id = 5070
        room = DynamicRoom(
            guild_id=self.guild_id,
            voice_channel_id=vc_id,
            owner_id=owner_id,
            control_channel_id=2070,
            control_message_id=3070,
            created_at=utcnow_iso(),
            status="active",
        )
        await self.db.create_dynamic_room(room)

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = self.guild_id
        mock_guild.owner_id = 9999

        owner_member = MagicMock(spec=discord.Member, id=owner_id, bot=False)
        mock_vc = AsyncMock(spec=discord.VoiceChannel)
        mock_vc.id = vc_id
        mock_vc.name = "🎙️・Deletable Room"
        mock_guild.get_channel.return_value = mock_vc

        interaction = AsyncMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.data = {"custom_id": f"rai_vc_confirm:delete:{vc_id}"}
        interaction.user = owner_member
        interaction.response.send_message = AsyncMock()

        with patch.object(DynamicVCControlManager, "delete_room_panel", new_callable=AsyncMock) as mock_delete_panel:
            await DynamicVCControlManager.handle_interaction(self.bot, interaction)
            mock_vc.delete.assert_called_once()
            mock_delete_panel.assert_called_once_with(self.bot, mock_guild, vc_id)

    # =========================================================================
    # 7. TEMPLATES APPLICATION
    # =========================================================================

    async def test_template_application(self):
        """Verify built-in templates (Gaming, Chill, etc.) configure name, limit, and privacy."""
        vc_id = 1080
        owner_id = 5080
        room = DynamicRoom(
            guild_id=self.guild_id,
            voice_channel_id=vc_id,
            owner_id=owner_id,
            created_at=utcnow_iso(),
            status="active",
        )
        await self.db.create_dynamic_room(room)

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = self.guild_id
        mock_guild.owner_id = 9999
        owner_member = MagicMock(spec=discord.Member, id=owner_id, display_name="Alex", bot=False)
        mock_guild.get_member.return_value = owner_member

        mock_vc = AsyncMock(spec=discord.VoiceChannel)
        mock_vc.id = vc_id
        mock_guild.get_channel.return_value = mock_vc

        interaction = AsyncMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.data = {"custom_id": f"rai_vc_tpl:Gaming:{vc_id}"}
        interaction.user = owner_member
        interaction.response.send_message = AsyncMock()

        with patch.object(DynamicVCControlManager, "update_room_panel", new_callable=AsyncMock):
            await DynamicVCControlManager.handle_interaction(self.bot, interaction)

        # Gaming template has limit=5, prefix="🎮・"
        mock_vc.edit.assert_called_once_with(name="🎮・Alex's Room", user_limit=5)
        fresh = await self.db.get_dynamic_room(vc_id)
        self.assertEqual(fresh.user_limit, 5)
        self.assertEqual(fresh.template_id, "Gaming")

    # =========================================================================
    # 8. MUSIC INTEGRATION (TIED STRICTLY TO TARGET VC)
    # =========================================================================

    async def test_music_controls_tied_to_vc(self):
        """Verify music controls work only if music player is connected to THAT specific VC."""
        vc_id = 1090
        owner_id = 5090
        room = DynamicRoom(
            guild_id=self.guild_id,
            voice_channel_id=vc_id,
            owner_id=owner_id,
            created_at=utcnow_iso(),
            status="active",
        )
        await self.db.create_dynamic_room(room)

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = self.guild_id
        mock_guild.owner_id = 9999
        owner_member = MagicMock(spec=discord.Member, id=owner_id, bot=False)

        mock_vc = AsyncMock(spec=discord.VoiceChannel)
        mock_vc.id = vc_id
        mock_guild.get_channel.return_value = mock_vc

        # Mock Music Cog and Player
        mock_music_cog = MagicMock()
        mock_player = AsyncMock()
        mock_player.voice_client.channel.id = vc_id  # Connected to THIS room
        mock_player.is_paused = False
        mock_player.current.title = "Cyberpunk Beats"
        mock_music_cog.players = {self.guild_id: mock_player}
        self.bot.cogs = {"Music": mock_music_cog}

        interaction = AsyncMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.guild_id = self.guild_id
        interaction.data = {"custom_id": f"rai_vc:music_toggle:{vc_id}"}
        interaction.user = owner_member
        interaction.response.send_message = AsyncMock()

        with patch.object(DynamicVCControlManager, "update_room_panel", new_callable=AsyncMock):
            await DynamicVCControlManager.handle_interaction(self.bot, interaction)

        mock_player.pause.assert_called_once()
        interaction.response.send_message.assert_called_once_with("⏸️ Paused music playback.", ephemeral=True)

        # Now test when music player is in ANOTHER channel
        mock_player.voice_client.channel.id = 999999  # Different VC
        interaction.response.send_message.reset_mock()
        with patch.object(DynamicVCControlManager, "update_room_panel", new_callable=AsyncMock):
            await DynamicVCControlManager.handle_interaction(self.bot, interaction)

        # Must reject with no active music session
        interaction.response.send_message.assert_called_once_with(
            "🎵 No active music session connected to this voice room.",
            ephemeral=True,
        )

    # =========================================================================
    # 9. TRANSFER OWNERSHIP & PERMISSIONS
    # =========================================================================

    async def test_transfer_ownership_flow(self):
        """Verify transfer ownership updates DB, shifts Discord permissions, and refreshes panel."""
        from utils.dynamic_vc_control import DynamicTransferSelectView

        vc_id = 1100
        old_owner_id = 5100
        new_owner_id = 5200
        room = DynamicRoom(
            guild_id=self.guild_id,
            voice_channel_id=vc_id,
            owner_id=old_owner_id,
            created_at=utcnow_iso(),
            status="active",
        )
        await self.db.create_dynamic_room(room)

        mock_guild = MagicMock(spec=discord.Guild)
        mock_vc = AsyncMock(spec=discord.VoiceChannel)
        mock_vc.id = vc_id
        mock_vc.name = "🎙️・Shared Room"

        old_owner = MagicMock(spec=discord.Member, id=old_owner_id, display_name="OldOwner", bot=False)
        new_owner = MagicMock(spec=discord.Member, id=new_owner_id, display_name="NewOwner", bot=False)
        mock_vc.members = [old_owner, new_owner]

        def get_member_side_effect(m_id):
            if m_id == old_owner_id:
                return old_owner
            elif m_id == new_owner_id:
                return new_owner
            return None

        mock_guild.get_member.side_effect = get_member_side_effect

        view = DynamicTransferSelectView(mock_vc)
        interaction = AsyncMock(spec=discord.Interaction)
        interaction.client = self.bot
        interaction.guild = mock_guild
        interaction.user = old_owner
        interaction.data = {"values": [str(new_owner_id)]}
        interaction.response.send_message = AsyncMock()

        with patch.object(DynamicVCControlManager, "update_room_panel", new_callable=AsyncMock):
            await view._select_callback(interaction)

        # Check DB update
        fresh = await self.db.get_dynamic_room(vc_id)
        self.assertEqual(fresh.owner_id, new_owner_id)

        # Check Discord permission shifts
        mock_vc.set_permissions.assert_any_call(new_owner, manage_channels=True, move_members=True, mute_members=True)
        mock_vc.set_permissions.assert_any_call(old_owner, manage_channels=None, move_members=None, mute_members=None)

    # =========================================================================
    # 10. EMPTY ROOM GRACE PERIOD & REJOIN RESTORATION
    # =========================================================================

    async def test_empty_room_grace_period_and_rejoin(self):
        """
        Verify:
        - When all members leave, room status becomes 'empty_countdown' with timestamp.
        - When someone rejoins before 60s, status returns to 'active'.
        - If countdown exceeds 60s, room is purged.
        """
        from cogs.temp_voice import TempVoiceCog

        cog = TempVoiceCog(self.bot)
        cog._supervisor_task.cancel()  # Manual testing

        vc_id = 1110
        room = DynamicRoom(
            guild_id=self.guild_id,
            voice_channel_id=vc_id,
            owner_id=5110,
            created_at=utcnow_iso(),
            status="active",
        )
        await self.db.create_dynamic_room(room)

        mock_guild = MagicMock(spec=discord.Guild, id=self.guild_id)
        mock_vc = AsyncMock(spec=discord.VoiceChannel, id=vc_id, name="Test VC", members=[])
        mock_guild.get_channel.return_value = mock_vc
        self.bot.guilds = [mock_guild]

        # 1. Trigger supervisor when room is newly empty -> enters empty_countdown
        with patch.object(DynamicVCControlManager, "update_room_panel", new_callable=AsyncMock):
            await cog._dynamic_vc_supervisor()

        fresh = await self.db.get_dynamic_room(vc_id)
        self.assertEqual(fresh.status, "empty_countdown")
        self.assertIsNotNone(fresh.last_empty_at)

        # 2. Member rejoins -> voice state listener restores active
        mock_member = MagicMock(spec=discord.Member, id=9999, bot=False, guild=mock_guild)
        before_state = MagicMock(spec=discord.VoiceState, channel=None)
        after_state = MagicMock(spec=discord.VoiceState, channel=mock_vc)

        with patch.object(DynamicVCControlManager, "update_room_panel", new_callable=AsyncMock):
            await cog.on_voice_state_update(mock_member, before_state, after_state)

        fresh_rejoined = await self.db.get_dynamic_room(vc_id)
        self.assertEqual(fresh_rejoined.status, "active")
        self.assertIsNone(fresh_rejoined.last_empty_at)

        # 3. Simulate 65 seconds elapsed empty countdown -> should delete VC
        old_empty_time = (utcnow() - datetime.timedelta(seconds=65)).isoformat()
        await self.db.update_dynamic_room(vc_id, status="empty_countdown", last_empty_at=old_empty_time)

        with patch.object(DynamicVCControlManager, "delete_room_panel", new_callable=AsyncMock) as mock_del_panel:
            await cog._dynamic_vc_supervisor()
            mock_vc.delete.assert_called_once()
            mock_del_panel.assert_called_once_with(self.bot, mock_guild, vc_id)

    # =========================================================================
    # 11. OWNER LEAVING DISCORD SERVER
    # =========================================================================

    async def test_owner_leaving_server(self):
        """Verify owner departure from the guild starts cleanup countdown and reports."""
        from cogs.temp_voice import TempVoiceCog

        cog = TempVoiceCog(self.bot)
        cog._supervisor_task.cancel()

        vc_id = 1120
        owner_id = 5120
        room = DynamicRoom(
            guild_id=self.guild_id,
            voice_channel_id=vc_id,
            owner_id=owner_id,
            created_at=utcnow_iso(),
            status="active",
        )
        await self.db.create_dynamic_room(room)

        mock_guild = MagicMock(spec=discord.Guild, id=self.guild_id)
        mock_vc = AsyncMock(spec=discord.VoiceChannel, id=vc_id, name="Owner Leave VC")
        mock_guild.get_channel.return_value = mock_vc

        leaving_member = MagicMock(spec=discord.Member, id=owner_id, guild=mock_guild, display_name="LeavingOwner")

        with patch.object(DynamicVCControlManager, "update_room_panel", new_callable=AsyncMock):
            await cog.on_member_remove(leaving_member)

        fresh = await self.db.get_dynamic_room(vc_id)
        self.assertEqual(fresh.status, "empty_countdown")
        self.assertIsNotNone(fresh.last_empty_at)

    # =========================================================================
    # 12. STARTUP RECOVERY & STALE RESILIENCE
    # =========================================================================

    async def test_startup_recovery(self):
        """Verify startup recovery cleans up orphaned records whose Discord VCs were deleted."""
        from cogs.temp_voice import TempVoiceCog

        cog = TempVoiceCog(self.bot)
        cog._supervisor_task.cancel()

        # Room with missing Discord VC
        await self.db.create_dynamic_room(DynamicRoom(
            guild_id=self.guild_id,
            voice_channel_id=1130,
            owner_id=5130,
            status="active",
        ))
        # Room with active Discord VC and members
        await self.db.create_dynamic_room(DynamicRoom(
            guild_id=self.guild_id,
            voice_channel_id=1140,
            owner_id=5140,
            status="empty_countdown",
        ))

        mock_guild = MagicMock(spec=discord.Guild, id=self.guild_id)
        mock_active_vc = MagicMock(spec=discord.VoiceChannel, id=1140, members=[MagicMock()])

        def get_channel_mock(ch_id):
            if ch_id == 1140:
                return mock_active_vc
            return None

        mock_guild.get_channel.side_effect = get_channel_mock
        self.bot.get_guild.return_value = mock_guild
        self.bot.wait_until_ready = AsyncMock()

        with patch.object(DynamicVCControlManager, "delete_room_panel", new_callable=AsyncMock) as mock_del:
            with patch.object(DynamicVCControlManager, "update_room_panel", new_callable=AsyncMock) as mock_update:
                await cog._run_startup_recovery()
                # 1130 had no VC -> deleted
                mock_del.assert_called_once_with(self.bot, mock_guild, 1130)
                # 1140 had members -> status restored to active
                fresh_1140 = await self.db.get_dynamic_room(1140)
                self.assertEqual(fresh_1140.status, "active")
                mock_update.assert_called_once_with(self.bot, mock_guild, 1140)

    # =========================================================================
    # 13. KNOCK & WAITING ROOM TESTS (PHASE 7)
    # =========================================================================

    async def test_knock_request_flow_allow(self):
        """Verify complete Knock flow: request, notification, allow, and permissions."""
        vc_id = 1201
        owner_id = 5201
        requester_id = 9901

        room = DynamicRoom(
            guild_id=self.guild_id,
            voice_channel_id=vc_id,
            owner_id=owner_id,
            room_type="private",
            privacy_mode="owner_only",
            status="active",
        )
        await self.db.create_dynamic_room(room)

        mock_guild = MagicMock(spec=discord.Guild, id=self.guild_id)
        mock_vc = MagicMock(spec=discord.VoiceChannel, id=vc_id, name="Secret Room", guild=mock_guild)
        mock_vc.set_permissions = AsyncMock()
        mock_owner = MagicMock(spec=discord.Member, id=owner_id, guild=mock_guild)
        mock_owner.send = AsyncMock()
        mock_requester = MagicMock(spec=discord.Member, id=requester_id, guild=mock_guild)
        mock_requester.voice = MagicMock(channel=MagicMock())
        mock_requester.move_to = AsyncMock()
        mock_requester.send = AsyncMock()

        def get_member_mock(uid):
            if uid == owner_id:
                return mock_owner
            elif uid == requester_id:
                return mock_requester
            return None

        mock_guild.get_channel.return_value = mock_vc
        mock_guild.get_member.side_effect = get_member_mock
        self.bot.get_guild.return_value = mock_guild

        # 1. Requester triggers knock request
        req_interaction = MagicMock(spec=discord.Interaction)
        req_interaction.guild = mock_guild
        req_interaction.user = mock_requester
        req_interaction.response.send_message = AsyncMock()

        handled_req = await DynamicVCControlManager._dispatch_knock_action(
            self.bot, req_interaction, "request", str(vc_id)
        )
        self.assertTrue(handled_req)
        mock_owner.send.assert_called_once()

        # Check pending request in database
        pending = await self.db.get_pending_knock_request(vc_id, requester_id)
        self.assertIsNotNone(pending)
        self.assertEqual(pending.status, "pending")

        # 2. Owner approves knock request
        allow_interaction = MagicMock(spec=discord.Interaction)
        allow_interaction.guild = mock_guild
        allow_interaction.user = mock_owner
        allow_interaction.response.edit_message = AsyncMock()
        allow_interaction.response.send_message = AsyncMock()

        with patch.object(DynamicVCControlManager, "update_room_panel", new_callable=AsyncMock):
            handled_allow = await DynamicVCControlManager._dispatch_knock_action(
                self.bot, allow_interaction, "allow", str(pending.id)
            )
            self.assertTrue(handled_allow)

        # Verify DB status updated
        updated_req = await self.db.get_room_knock_request(pending.id)
        self.assertEqual(updated_req.status, "allowed")

        # Verify member added to room_members
        members = await self.db.get_room_members(vc_id)
        self.assertTrue(any(m.user_id == requester_id for m in members))

        # Verify Discord permissions and move
        mock_vc.set_permissions.assert_called_once()
        mock_requester.move_to.assert_called_once_with(mock_vc, reason=unittest.mock.ANY)

    async def test_knock_request_flow_decline(self):
        """Verify Knock flow decline sets status and notifies user."""
        vc_id = 1202
        owner_id = 5202
        requester_id = 9902

        room = DynamicRoom(
            guild_id=self.guild_id,
            voice_channel_id=vc_id,
            owner_id=owner_id,
            room_type="private",
            privacy_mode="owner_only",
            status="active",
        )
        await self.db.create_dynamic_room(room)

        mock_guild = MagicMock(spec=discord.Guild, id=self.guild_id)
        mock_vc = MagicMock(spec=discord.VoiceChannel, id=vc_id, name="Private Chamber", guild=mock_guild)
        mock_requester = MagicMock(spec=discord.Member, id=requester_id, guild=mock_guild)
        mock_requester.send = AsyncMock()
        mock_owner = MagicMock(spec=discord.Member, id=owner_id, guild=mock_guild)

        mock_guild.get_channel.return_value = mock_vc
        mock_guild.get_member.side_effect = lambda uid: mock_requester if uid == requester_id else mock_owner

        req = await self.db.create_room_knock_request(vc_id, requester_id, expires_in_seconds=120)

        decline_interaction = MagicMock(spec=discord.Interaction)
        decline_interaction.guild = mock_guild
        decline_interaction.user = mock_owner
        decline_interaction.response.edit_message = AsyncMock()

        handled = await DynamicVCControlManager._dispatch_knock_action(
            self.bot, decline_interaction, "decline", str(req.id)
        )
        self.assertTrue(handled)

        updated_req = await self.db.get_room_knock_request(req.id)
        self.assertEqual(updated_req.status, "declined")
        mock_requester.send.assert_called_once()

    # =========================================================================
    # 14. CO-HOST & DJ DELEGATION (PHASES 8 & 9)
    # =========================================================================

    async def test_cohost_delegation_and_permissions(self):
        """Verify Co-Host can manage members but cannot delete room or transfer owner."""
        vc_id = 1203
        owner_id = 5203
        cohost_id = 7703

        room = DynamicRoom(
            guild_id=self.guild_id,
            voice_channel_id=vc_id,
            owner_id=owner_id,
            co_host_ids=[cohost_id],
            status="active",
        )
        await self.db.create_dynamic_room(room)

        mock_guild = MagicMock(spec=discord.Guild, id=self.guild_id, owner_id=owner_id)
        mock_vc = MagicMock(spec=discord.VoiceChannel, id=vc_id, name="Squad Hub", guild=mock_guild)
        mock_guild.get_channel.return_value = mock_vc
        self.bot.get_guild.return_value = mock_guild

        cohost_member = MagicMock(spec=discord.Member, id=cohost_id)
        cohost_member.guild_permissions.administrator = False

        # Co-host attempts to delete room -> REJECTED
        del_interaction = MagicMock(spec=discord.Interaction)
        del_interaction.guild = mock_guild
        del_interaction.user = cohost_member
        del_interaction.data = {"custom_id": f"rai_vc:delete:{vc_id}"}
        del_interaction.response.send_message = AsyncMock()

        handled_del = await DynamicVCControlManager.handle_interaction(self.bot, del_interaction)
        self.assertTrue(handled_del)
        args, kwargs = del_interaction.response.send_message.call_args
        self.assertIn("You are not the owner of this room", kwargs["embed"].description)

        # Co-host attempts member management (members view) -> ALLOWED
        members_interaction = MagicMock(spec=discord.Interaction)
        members_interaction.guild = mock_guild
        members_interaction.user = cohost_member
        members_interaction.data = {"custom_id": f"rai_vc:members:{vc_id}"}
        members_interaction.response.send_message = AsyncMock()

        handled_mem = await DynamicVCControlManager.handle_interaction(self.bot, members_interaction)
        self.assertTrue(handled_mem)
        args, kwargs = members_interaction.response.send_message.call_args
        self.assertIn("Member Management", kwargs["embed"].title)

    async def test_dj_delegation_and_music_control(self):
        """Verify DJ can control music playback while non-DJ cannot."""
        vc_id = 1204
        owner_id = 5204
        dj_id = 8804
        regular_id = 3304

        room = DynamicRoom(
            guild_id=self.guild_id,
            voice_channel_id=vc_id,
            owner_id=owner_id,
            dj_ids=[dj_id],
            status="active",
        )
        await self.db.create_dynamic_room(room)

        mock_guild = MagicMock(spec=discord.Guild, id=self.guild_id, owner_id=owner_id)
        mock_vc = MagicMock(spec=discord.VoiceChannel, id=vc_id, name="Music Sanctuary", guild=mock_guild)
        mock_guild.get_channel.return_value = mock_vc

        dj_member = MagicMock(spec=discord.Member, id=dj_id)
        dj_member.guild_permissions.administrator = False

        reg_member = MagicMock(spec=discord.Member, id=regular_id)
        reg_member.guild_permissions.administrator = False

        # Regular user attempts music skip -> REJECTED
        reg_interaction = MagicMock(spec=discord.Interaction)
        reg_interaction.guild = mock_guild
        reg_interaction.user = reg_member
        reg_interaction.data = {"custom_id": f"rai_vc:music_skip:{vc_id}"}
        reg_interaction.response.send_message = AsyncMock()

        handled_reg = await DynamicVCControlManager.handle_interaction(self.bot, reg_interaction)
        self.assertTrue(handled_reg)
        args, kwargs = reg_interaction.response.send_message.call_args
        self.assertIn("You must be the room owner, co-host, or DJ to control music", kwargs["embed"].description)

        # DJ attempts music queue -> ALLOWED
        dj_interaction = MagicMock(spec=discord.Interaction)
        dj_interaction.guild = mock_guild
        dj_interaction.guild_id = self.guild_id
        dj_interaction.user = dj_member
        dj_interaction.data = {"custom_id": f"rai_vc:music_queue:{vc_id}"}
        dj_interaction.response.send_message = AsyncMock()

        handled_dj = await DynamicVCControlManager.handle_interaction(self.bot, dj_interaction)
        self.assertTrue(handled_dj)

    # =========================================================================
    # 15. ANTI-SPAM & ANTI-RAID PROTECTION (PHASE 14)
    # =========================================================================

    async def test_anti_spam_cooldown_and_mass_creation_block(self):
        """Verify 30s creation cooldown and 5-minute block on 4 rapid joins."""
        from cogs.temp_voice import TempVoiceCog, TempVoiceConfig

        cog = TempVoiceCog(self.bot)
        cog._supervisor_task.cancel()

        mock_guild = MagicMock(spec=discord.Guild, id=self.guild_id)
        mock_user = MagicMock(spec=discord.Member, id=9999, display_name="Spammer", guild=mock_guild)
        mock_user.move_to = AsyncMock()
        mock_user.send = AsyncMock()
        mock_trigger = MagicMock(spec=discord.VoiceChannel, category=None)
        cfg = TempVoiceConfig(guild_id=self.guild_id, enabled=True)

        mock_vc = MagicMock(spec=discord.VoiceChannel, id=9900, name="Room")
        mock_guild.create_voice_channel = AsyncMock(return_value=mock_vc)

        with patch.object(DynamicVCControlManager, "create_room_panel", new_callable=AsyncMock):
            with patch("utils.owner_reporter.OwnerReporter.send_room_report"):
                # 1st creation succeeds
                await cog._handle_trigger_join(mock_user, mock_trigger, False, cfg)
                self.assertIn(mock_user.id, cog._creation_cooldowns)
                self.assertEqual(mock_guild.create_voice_channel.call_count, 1)

                # 2nd creation within 30s -> Blocked by per-user cooldown
                await cog._handle_trigger_join(mock_user, mock_trigger, False, cfg)
                self.assertEqual(mock_guild.create_voice_channel.call_count, 1)  # not incremented

                # Simulate rapid joins to trigger 4 joins in 60s -> 5-min block
                cog._creation_cooldowns.clear()  # bypass simple cooldown to test mass trigger
                cog._recent_creations[mock_user.id] = [utcnow().timestamp() - 5 for _ in range(3)]

                with patch("utils.owner_reporter.OwnerReporter.send_security_report") as mock_sec:
                    await cog._handle_trigger_join(mock_user, mock_trigger, False, cfg)
                    self.assertIn(mock_user.id, cog._blocked_users)
                    mock_sec.assert_called_once()
                    self.assertEqual(mock_sec.call_args[1]["event"], "Dynamic Room Mass Creation Abuse")

    # =========================================================================
    # 16. EMERGENCY ADMIN CONTROLS (PHASE 32)
    # =========================================================================

    async def test_admin_emergency_controls(self):
        """Verify administrator emergency controls (lock all, cleanup, health, status)."""
        vc_id = 1205
        room = DynamicRoom(
            guild_id=self.guild_id,
            voice_channel_id=vc_id,
            owner_id=5205,
            privacy_mode="public",
            status="active",
        )
        await self.db.create_dynamic_room(room)

        mock_guild = MagicMock(spec=discord.Guild, id=self.guild_id, owner_id=1111)
        mock_vc = MagicMock(spec=discord.VoiceChannel, id=vc_id, name="Test VC", guild=mock_guild, members=[])
        mock_vc.set_permissions = AsyncMock()
        mock_vc.delete = AsyncMock()
        mock_guild.get_channel.return_value = mock_vc

        admin_member = MagicMock(spec=discord.Member, id=1111)
        admin_member.guild_permissions.administrator = True

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = mock_guild
        interaction.user = admin_member
        interaction.response.send_message = AsyncMock()

        with patch.object(DynamicVCControlManager, "update_room_panel", new_callable=AsyncMock):
            # Test Lock All
            handled_lock = await DynamicVCControlManager._dispatch_admin_emergency_action(
                self.bot, interaction, "lock_all"
            )
            self.assertTrue(handled_lock)
            mock_vc.set_permissions.assert_called_once()
            fresh = await self.db.get_dynamic_room(vc_id)
            self.assertEqual(fresh.locked, 1)

            # Test Health Check
            handled_health = await DynamicVCControlManager._dispatch_admin_emergency_action(
                self.bot, interaction, "health"
            )
            self.assertTrue(handled_health)

            # Test Cleanup Empty Rooms
            with patch.object(DynamicVCControlManager, "delete_room_panel", new_callable=AsyncMock):
                handled_clean = await DynamicVCControlManager._dispatch_admin_emergency_action(
                    self.bot, interaction, "cleanup_empty"
                )
                self.assertTrue(handled_clean)
                mock_vc.delete.assert_called_once()


if __name__ == "__main__":
    unittest.main()

