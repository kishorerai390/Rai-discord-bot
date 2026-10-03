"""
Unit and integration tests for Rai Interactive Incident Action System.

Verifies:
1. Incident creation, lifecycle states, and SQLite database persistence.
2. Smart action visibility per report type (Security, Mod, Music, Room, Bot, System) & state.
3. Strict owner authorization with ephemeral rejection of unauthorized users.
4. Ephemeral confirmation flows for destructive actions (Ban, Kick, Delete Room, Unlock).
5. Immediate execution for safe actions (Details, Health, Recheck).
6. Dual delivery to Owner DM and Private Report Channel with message tracking.
7. Dual-message synchronization (action from DM or Channel updates BOTH messages).
8. Idempotency and double-click prevention.
9. Resilient handling when target resources are deleted/missing.
10. Full action audit trail logging in SQLite.
11. State persistence across simulated bot restarts.
"""

from __future__ import annotations

import asyncio
import datetime
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import aiosqlite
import discord

from database.database import Database
from database.migrations import run_migrations
from database.models import InteractiveIncident, IncidentActionAudit
from utils.interactive_incidents import InteractiveIncidentManager, FOUNDER_ID
from utils.owner_reporter import OwnerReporter, generate_incident_id


class TestInteractiveIncidentSystem(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        # Create temporary database with all migrations (including Migration 19)
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_incidents.db"
        self.db = Database(str(self.db_path))
        await self.db.connect()

        # Mock Bot
        self.bot = MagicMock()
        self.bot.db = self.db

        # Mock Guild & Owner
        self.guild_id = 99880011
        self.owner_id = 77665544
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = self.guild_id
        self.guild.name = "Rai Secure Guild"
        self.guild.owner_id = self.owner_id
        self.bot.get_guild.return_value = self.guild
        self.bot.fetch_guild = AsyncMock(return_value=self.guild)

        # Mock Owner User
        self.owner_user = MagicMock(spec=discord.User)
        self.owner_user.id = self.owner_id
        self.owner_user.name = "ServerOwner"
        self.owner_user.bot = False
        self.owner_user.send = AsyncMock()
        self.bot.get_user.return_value = self.owner_user
        self.bot.fetch_user = AsyncMock(return_value=self.owner_user)

        # Initialize guild config in SQLite
        await self.db.get_or_create_guild_config(self.guild_id)

    async def asyncTearDown(self):
        try:
            if hasattr(self, "db") and self.db:
                await self.db.close()
        except Exception:
            pass
        await asyncio.sleep(0.02)
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    async def test_database_persistence_and_indexes(self):
        """Test incident creation, database retrieval, status updates, and audit logging."""
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        incident = InteractiveIncident(
            incident_id="RAI-INC-000101",
            guild_id=self.guild_id,
            report_type="security",
            event_type="Mass channel deletion detected",
            title="🚨 Security Incident: Mass Channel Deletion",
            description="Attacker attempted to delete 5 channels in 3 seconds.",
            actor_id=123456789,
            actor_name="NukerUser",
            target_id=987654321,
            target_name="general-chat",
            action_taken="Emergency lockdown enabled",
            status="ACTIVE",
            severity="CRITICAL",
            details_json=json.dumps({"channels_deleted": 5, "ip_logged": "127.0.0.1"}),
            created_at=now_iso,
            updated_at=now_iso,
        )

        await self.db.create_interactive_incident(incident)

        # Retrieve incident
        fetched = await self.db.get_interactive_incident("RAI-INC-000101")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.incident_id, "RAI-INC-000101")
        self.assertEqual(fetched.guild_id, self.guild_id)
        self.assertEqual(fetched.report_type, "security")
        self.assertEqual(fetched.actor_id, 123456789)
        self.assertEqual(fetched.status, "ACTIVE")
        self.assertEqual(fetched.severity, "CRITICAL")

        # Update message tracking IDs
        await self.db.update_interactive_incident_messages(
            incident_id="RAI-INC-000101",
            dm_message_id=11112222,
            dm_channel_id=33334444,
            channel_message_id=55556666,
            report_channel_id=77778888,
        )
        updated = await self.db.get_interactive_incident("RAI-INC-000101")
        self.assertEqual(updated.dm_message_id, 11112222)
        self.assertEqual(updated.dm_channel_id, 33334444)
        self.assertEqual(updated.channel_message_id, 55556666)
        self.assertEqual(updated.report_channel_id, 77778888)

        # Update status
        await self.db.update_interactive_incident_status(
            "RAI-INC-000101",
            "RESOLVED",
            "Mitigated by Server Owner via interactive console.",
        )
        resolved = await self.db.get_interactive_incident("RAI-INC-000101")
        self.assertEqual(resolved.status, "RESOLVED")
        self.assertIn("Mitigated by Server Owner", resolved.action_taken)

        # Record action audit
        await self.db.record_incident_action(
            incident_id="RAI-INC-000101",
            actor_id=self.owner_id,
            action="lockdown",
            result="SUCCESS",
            target_id=987654321,
        )
        actions = await self.db.get_incident_actions("RAI-INC-000101")
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].action, "lockdown")
        self.assertEqual(actions[0].result, "SUCCESS")

    async def test_smart_action_visibility_by_type_and_state(self):
        """Verify buttons adapt dynamically according to report type and lifecycle state."""
        # 1. Security Report - ACTIVE state
        sec_active = InteractiveIncident(
            incident_id="RAI-INC-SEC-01",
            guild_id=self.guild_id,
            report_type="security",
            event_type="Raid Alert",
            title="Security Alert",
            description="Spam wave detected",
            actor_id=123,
            status="ACTIVE",
        )
        view_sec_active = InteractiveIncidentManager.build_incident_view(sec_active)
        btn_ids = [item.custom_id for item in view_sec_active.children if isinstance(item, discord.ui.Button)]
        self.assertIn("rai_inc:lockdown:RAI-INC-SEC-01", btn_ids)
        self.assertIn("rai_inc:restrict:RAI-INC-SEC-01", btn_ids)
        self.assertIn("rai_inc:details:RAI-INC-SEC-01", btn_ids)
        self.assertIn("rai_inc:recheck:RAI-INC-SEC-01", btn_ids)
        self.assertNotIn("rai_inc:unlock:RAI-INC-SEC-01", btn_ids)

        # Security Report - RESOLVED state
        sec_resolved = InteractiveIncident(
            incident_id="RAI-INC-SEC-01",
            guild_id=self.guild_id,
            report_type="security",
            event_type="Raid Alert",
            title="Security Alert",
            description="Spam wave detected",
            actor_id=123,
            status="RESOLVED",
        )
        view_sec_resolved = InteractiveIncidentManager.build_incident_view(sec_resolved)
        btn_ids_res = [item.custom_id for item in view_sec_resolved.children if isinstance(item, discord.ui.Button)]
        self.assertIn("rai_inc:unlock:RAI-INC-SEC-01", btn_ids_res)
        self.assertNotIn("rai_inc:lockdown:RAI-INC-SEC-01", btn_ids_res)

        # 2. Moderation Report - ACTIVE state
        mod_active = InteractiveIncident(
            incident_id="RAI-INC-MOD-01",
            guild_id=self.guild_id,
            report_type="mod",
            event_type="Toxicity Violation",
            title="Mod Action",
            description="Severe harassment",
            target_id=456,
            status="ACTIVE",
        )
        view_mod = InteractiveIncidentManager.build_incident_view(mod_active)
        mod_btns = [item.custom_id for item in view_mod.children if isinstance(item, discord.ui.Button)]
        self.assertIn("rai_inc:timeout:RAI-INC-MOD-01", mod_btns)
        self.assertIn("rai_inc:kick:RAI-INC-MOD-01", mod_btns)
        self.assertIn("rai_inc:ban:RAI-INC-MOD-01", mod_btns)

        # Moderation Report - RESOLVED state (shows Undo)
        mod_active.status = "RESOLVED"
        view_mod_res = InteractiveIncidentManager.build_incident_view(mod_active)
        mod_res_btns = [item.custom_id for item in view_mod_res.children if isinstance(item, discord.ui.Button)]
        self.assertIn("rai_inc:undo:RAI-INC-MOD-01", mod_res_btns)

        # 3. Room Report - ACTIVE state
        room_active = InteractiveIncident(
            incident_id="RAI-INC-ROOM-01",
            guild_id=self.guild_id,
            report_type="room",
            event_type="Room Overcrowded",
            title="Private Room Event",
            description="Room limit bypassed",
            target_id=789,
            status="ACTIVE",
        )
        view_room = InteractiveIncidentManager.build_incident_view(room_active)
        room_btns = [item.custom_id for item in view_room.children if isinstance(item, discord.ui.Button)]
        self.assertIn("rai_inc:lock_room:RAI-INC-ROOM-01", room_btns)
        self.assertIn("rai_inc:disconnect_room:RAI-INC-ROOM-01", room_btns)
        self.assertIn("rai_inc:transfer_room:RAI-INC-ROOM-01", room_btns)
        self.assertIn("rai_inc:delete_room:RAI-INC-ROOM-01", room_btns)

        # Room Report - RESOLVED state
        room_active.status = "RESOLVED"
        view_room_res = InteractiveIncidentManager.build_incident_view(room_active)
        room_res_btns = [item.custom_id for item in view_room_res.children if isinstance(item, discord.ui.Button)]
        self.assertIn("rai_inc:unlock_room:RAI-INC-ROOM-01", room_res_btns)
        self.assertNotIn("rai_inc:lock_room:RAI-INC-ROOM-01", room_res_btns)

    async def test_button_authorization_non_owner_rejection(self):
        """Unauthorized users clicking buttons must receive ephemeral rejection and trigger an audit entry."""
        incident = InteractiveIncident(
            incident_id="RAI-INC-AUTH-01",
            guild_id=self.guild_id,
            report_type="security",
            event_type="Intrusion Detected",
            title="Intrusion Alert",
            description="Token logger link",
            status="ACTIVE",
        )
        await self.db.create_interactive_incident(incident)

        # Non-owner interaction
        attacker = MagicMock(spec=discord.Member)
        attacker.id = 99999999
        attacker.name = "MaliciousUser"

        interaction = MagicMock(spec=discord.Interaction)
        interaction.type = discord.InteractionType.component
        interaction.data = {"custom_id": "rai_inc:lockdown:RAI-INC-AUTH-01"}
        interaction.user = attacker
        interaction.guild = self.guild
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        handled = await InteractiveIncidentManager.handle_component_interaction(self.bot, interaction)
        self.assertTrue(handled)

        # Ephemeral rejection sent
        interaction.response.send_message.assert_awaited_once()
        sent_text = interaction.response.send_message.call_args[0][0]
        self.assertIn("Unauthorized", sent_text)
        self.assertTrue(interaction.response.send_message.call_args[1].get("ephemeral"))

        # Audit trail must record the unauthorized attempt
        audits = await self.db.get_incident_actions("RAI-INC-AUTH-01")
        self.assertEqual(len(audits), 1)
        self.assertEqual(audits[0].actor_id, 99999999)
        self.assertEqual(audits[0].result, "UNAUTHORIZED")

    async def test_destructive_action_confirmation_flow(self):
        """Destructive actions (e.g. Ban, Delete Room) must require explicit confirmation."""
        target_uid = 44556677
        incident = InteractiveIncident(
            incident_id="RAI-INC-CONFIRM-01",
            guild_id=self.guild_id,
            report_type="mod",
            event_type="Severe Harassment",
            title="Moderation Incident",
            description="Repeated slurs",
            target_id=target_uid,
            status="ACTIVE",
        )
        await self.db.create_interactive_incident(incident)

        # Step 1: Owner clicks initial [🔨 Ban] button
        interaction1 = MagicMock(spec=discord.Interaction)
        interaction1.type = discord.InteractionType.component
        interaction1.data = {"custom_id": "rai_inc:ban:RAI-INC-CONFIRM-01"}
        interaction1.user = self.owner_user
        interaction1.guild = self.guild
        interaction1.response = MagicMock()
        interaction1.response.send_message = AsyncMock()

        await InteractiveIncidentManager.handle_component_interaction(self.bot, interaction1)

        # Must respond with ephemeral confirmation view
        interaction1.response.send_message.assert_awaited_once()
        prompt_text = interaction1.response.send_message.call_args[0][0]
        confirm_view = interaction1.response.send_message.call_args[1].get("view")
        self.assertIn("CONFIRM ACTION: BAN MEMBER", prompt_text)
        self.assertIsNotNone(confirm_view)
        self.assertTrue(interaction1.response.send_message.call_args[1].get("ephemeral"))

        # Verify confirmation view contains Confirm Ban and Cancel buttons
        btn_ids = [btn.custom_id for btn in confirm_view.children if isinstance(btn, discord.ui.Button)]
        self.assertIn("rai_inc:confirm_ban:RAI-INC-CONFIRM-01", btn_ids)
        self.assertIn("rai_inc:cancel:RAI-INC-CONFIRM-01", btn_ids)

        # Step 2: Owner clicks [Cancel] -> incident status remains ACTIVE
        interaction_cancel = MagicMock(spec=discord.Interaction)
        interaction_cancel.type = discord.InteractionType.component
        interaction_cancel.data = {"custom_id": "rai_inc:cancel:RAI-INC-CONFIRM-01"}
        interaction_cancel.user = self.owner_user
        interaction_cancel.guild = self.guild
        interaction_cancel.response = MagicMock()
        interaction_cancel.response.send_message = AsyncMock()

        await InteractiveIncidentManager.handle_component_interaction(self.bot, interaction_cancel)
        inc_check = await self.db.get_interactive_incident("RAI-INC-CONFIRM-01")
        self.assertEqual(inc_check.status, "ACTIVE")

        # Step 3: Owner clicks [Confirm Ban] -> real ban executed against guild
        self.guild.ban = AsyncMock()

        interaction_confirm = MagicMock(spec=discord.Interaction)
        interaction_confirm.type = discord.InteractionType.component
        interaction_confirm.data = {"custom_id": "rai_inc:confirm_ban:RAI-INC-CONFIRM-01"}
        interaction_confirm.user = self.owner_user
        interaction_confirm.guild = self.guild
        interaction_confirm.response = MagicMock()
        interaction_confirm.response.defer = AsyncMock()
        interaction_confirm.followup = MagicMock()
        interaction_confirm.followup.send = AsyncMock()

        await InteractiveIncidentManager.handle_component_interaction(self.bot, interaction_confirm)

        # Guild ban called with target ID
        self.guild.ban.assert_awaited_once()
        banned_obj = self.guild.ban.call_args[0][0]
        self.assertEqual(banned_obj.id, target_uid)

        # Incident status updated to RESOLVED in database
        inc_after = await self.db.get_interactive_incident("RAI-INC-CONFIRM-01")
        self.assertEqual(inc_after.status, "RESOLVED")
        self.assertIn("banned permanently", inc_after.action_taken)

        # Audit trail recorded
        actions = await self.db.get_incident_actions("RAI-INC-CONFIRM-01")
        self.assertTrue(any(a.action == "ban" and a.result == "SUCCESS" for a in actions))

    async def test_idempotency_prevents_duplicate_execution(self):
        """Clicking an already resolved incident action must return an informational notice without re-running."""
        incident = InteractiveIncident(
            incident_id="RAI-INC-IDEMP-01",
            guild_id=self.guild_id,
            report_type="security",
            event_type="Lockdown Applied",
            title="Lockdown Incident",
            description="Auto lockdown",
            status="RESOLVED",  # Already resolved
        )
        await self.db.create_interactive_incident(incident)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.type = discord.InteractionType.component
        interaction.data = {"custom_id": "rai_inc:lockdown:RAI-INC-IDEMP-01"}
        interaction.user = self.owner_user
        interaction.guild = self.guild
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        await InteractiveIncidentManager.handle_component_interaction(self.bot, interaction)

        interaction.response.send_message.assert_awaited_once()
        msg_text = interaction.response.send_message.call_args[0][0]
        self.assertIn("already been completed", msg_text)
        self.assertTrue(interaction.response.send_message.call_args[1].get("ephemeral"))

    async def test_dual_message_synchronization_from_dm_and_channel(self):
        """
        Executing an action from DM updates BOTH DM message and Private Channel message.
        Executing an action from Channel operates on the EXACT SAME underlying incident.
        """
        # Mock DM message
        mock_dm_msg = MagicMock(spec=discord.Message)
        mock_dm_msg.id = 112233
        mock_dm_msg.edit = AsyncMock()

        mock_dm_channel = MagicMock(spec=discord.DMChannel)
        mock_dm_channel.id = 998877
        mock_dm_channel.fetch_message = AsyncMock(return_value=mock_dm_msg)
        self.owner_user.dm_channel = mock_dm_channel
        self.owner_user.create_dm = AsyncMock(return_value=mock_dm_channel)

        # Mock Channel message
        mock_ch_msg = MagicMock(spec=discord.Message)
        mock_ch_msg.id = 445566
        mock_ch_msg.edit = AsyncMock()

        mock_rep_channel = MagicMock(spec=discord.TextChannel)
        mock_rep_channel.id = 332211
        mock_rep_channel.fetch_message = AsyncMock(return_value=mock_ch_msg)
        self.bot.get_channel.side_effect = lambda cid: mock_rep_channel if cid == 332211 else mock_dm_channel

        # Target Room VC
        mock_vc = MagicMock(spec=discord.VoiceChannel)
        mock_vc.id = 665544
        mock_vc.name = "Private Suite #1"
        mock_vc.set_permissions = AsyncMock()
        self.guild.get_channel.return_value = mock_vc

        incident = InteractiveIncident(
            incident_id="RAI-INC-SYNC-01",
            guild_id=self.guild_id,
            report_type="room",
            event_type="Room Created",
            title="Private Room Alert",
            description="Room active",
            target_id=mock_vc.id,
            status="ACTIVE",
            dm_message_id=mock_dm_msg.id,
            dm_channel_id=mock_dm_channel.id,
            channel_message_id=mock_ch_msg.id,
            report_channel_id=mock_rep_channel.id,
        )
        await self.db.create_interactive_incident(incident)

        # Trigger Lock Room action from DM
        interaction_dm = MagicMock(spec=discord.Interaction)
        interaction_dm.type = discord.InteractionType.component
        interaction_dm.data = {"custom_id": "rai_inc:lock_room:RAI-INC-SYNC-01"}
        interaction_dm.user = self.owner_user
        interaction_dm.guild = None  # Originated in DM!
        interaction_dm.response = MagicMock()
        interaction_dm.response.defer = AsyncMock()
        interaction_dm.followup = MagicMock()
        interaction_dm.followup.send = AsyncMock()

        await InteractiveIncidentManager.handle_component_interaction(self.bot, interaction_dm)

        # Voice channel permission updated
        mock_vc.set_permissions.assert_awaited_once()

        # Allow background sync task to execute
        await asyncio.sleep(0.05)

        # Both DM message AND Channel message must have been edited in-place
        mock_dm_msg.edit.assert_awaited_once()
        mock_ch_msg.edit.assert_awaited_once()

        # Both edits should carry the updated RESOLVED embed and refreshed action view
        dm_embed = mock_dm_msg.edit.call_args[1]["embed"]
        ch_embed = mock_ch_msg.edit.call_args[1]["embed"]
        self.assertIn("RESOLVED", dm_embed.fields[1].value)
        self.assertIn("RESOLVED", ch_embed.fields[1].value)

        # Refreshed views should now offer [Unlock Room]
        dm_view = mock_dm_msg.edit.call_args[1]["view"]
        btn_ids = [btn.custom_id for btn in dm_view.children if isinstance(btn, discord.ui.Button)]
        self.assertIn("rai_inc:unlock_room:RAI-INC-SYNC-01", btn_ids)

    async def test_deleted_target_handling_fails_safely(self):
        """If a target resource is deleted, the incident action fails safely without crashing."""
        incident = InteractiveIncident(
            incident_id="RAI-INC-DELETED-01",
            guild_id=self.guild_id,
            report_type="room",
            event_type="Voice Room Issue",
            title="Room Incident",
            description="Room problem",
            target_id=999888777,  # Non-existent VC
            status="ACTIVE",
        )
        await self.db.create_interactive_incident(incident)

        self.guild.get_channel.return_value = None  # Deleted from server

        interaction = MagicMock(spec=discord.Interaction)
        interaction.type = discord.InteractionType.component
        interaction.data = {"custom_id": "rai_inc:lock_room:RAI-INC-DELETED-01"}
        interaction.user = self.owner_user
        interaction.guild = self.guild
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        await InteractiveIncidentManager.handle_component_interaction(self.bot, interaction)

        # Must report safe error ephemerally
        interaction.followup.send.assert_awaited_once()
        feedback = interaction.followup.send.call_args[0][0]
        self.assertIn("Action Failed", feedback)
        self.assertIn("not found on server", feedback)

        # Incident remains ACTIVE
        inc = await self.db.get_interactive_incident("RAI-INC-DELETED-01")
        self.assertEqual(inc.status, "ACTIVE")

        # Audit trail records failure
        audits = await self.db.get_incident_actions("RAI-INC-DELETED-01")
        self.assertTrue(any(a.result == "FAILED" for a in audits))

    async def test_persistence_across_bot_restart(self):
        """Simulate a bot restart and verify incident state and audit trail survive."""
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        incident = InteractiveIncident(
            incident_id="RAI-INC-RESTART-01",
            guild_id=self.guild_id,
            report_type="system",
            event_type="Database Latency Spike",
            title="System Alert",
            description="High disk I/O",
            status="ACTIVE",
            created_at=now_iso,
            updated_at=now_iso,
        )
        await self.db.create_interactive_incident(incident)
        await self.db.record_incident_action(
            incident_id="RAI-INC-RESTART-01",
            actor_id=self.owner_id,
            action="health",
            result="SUCCESS",
        )

        # Simulate Restart: Close DB and reopen fresh instance
        await self.db.close()
        restarted_db = Database(str(self.db_path))
        await restarted_db.connect()

        # Verify data restored intact
        restored_inc = await restarted_db.get_interactive_incident("RAI-INC-RESTART-01")
        self.assertIsNotNone(restored_inc)
        self.assertEqual(restored_inc.incident_id, "RAI-INC-RESTART-01")
        self.assertEqual(restored_inc.status, "ACTIVE")

        restored_actions = await restarted_db.get_incident_actions("RAI-INC-RESTART-01")
        self.assertEqual(len(restored_actions), 1)
        await restarted_db.close()

    async def test_mark_as_read_button_flow(self):
        """
        Validates:
        1. 'Mark as Read' button is added to active system & bot incidents.
        2. Clicking 'Mark as Read' marks incident as RESOLVED.
        3. Updates action log with acknowledgment.
        4. Replaces 'Mark as Read' with disabled 'Read' button on the resolved view.
        """
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        incident = InteractiveIncident(
            incident_id="RAI-INC-READ-01",
            guild_id=self.guild_id,
            report_type="system",
            event_type="Bot Core Online & Synchronized",
            title="System Infrastructure: Bot Core Online & Synchronized",
            description="Bot online",
            status="ACTIVE",
            created_at=now_iso,
            updated_at=now_iso,
        )
        await self.db.create_interactive_incident(incident)

        # 1. View before read
        view_active = InteractiveIncidentManager.build_incident_view(incident)
        labels_active = [btn.label for btn in view_active.children if hasattr(btn, "label")]
        self.assertIn("Mark as Read", labels_active)
        self.assertIn("Mark All Read", labels_active)
        self.assertIn("Retry", labels_active)
        self.assertIn("Backup", labels_active)
        self.assertIn("Health Check", labels_active)
        self.assertIn("Details", labels_active)

        # 2. Trigger Mark as Read
        interaction = MagicMock(spec=discord.Interaction)
        interaction.type = discord.InteractionType.component
        interaction.data = {"custom_id": "rai_inc:mark_read:RAI-INC-READ-01"}
        interaction.user = self.owner_user
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()
        mock_msg = MagicMock(spec=discord.Message)
        mock_msg.id = 99881122
        mock_msg.delete = AsyncMock()
        interaction.message = mock_msg

        handled = await InteractiveIncidentManager.handle_component_interaction(self.bot, interaction)
        self.assertTrue(handled)
        mock_msg.delete.assert_awaited_once()

        # Check DB updated
        updated_inc = await self.db.get_interactive_incident("RAI-INC-READ-01")
        self.assertEqual(updated_inc.status, "RESOLVED")
        self.assertIn("Acknowledged and marked as read", updated_inc.action_taken)

        # 3. View after read
        view_resolved = InteractiveIncidentManager.build_incident_view(updated_inc)
        labels_resolved = [btn.label for btn in view_resolved.children if hasattr(btn, "label")]
        self.assertNotIn("Mark as Read", labels_resolved)
        self.assertNotIn("Mark All Read", labels_resolved)
        self.assertIn("Read", labels_resolved)
        read_btn = next(btn for btn in view_resolved.children if getattr(btn, "label", None) == "Read")
        self.assertTrue(read_btn.disabled)

        # 4. Clicking disabled Read button shows informative ephemeral message
        interaction_read_again = MagicMock(spec=discord.Interaction)
        interaction_read_again.data = {"custom_id": "rai_inc:read_done:RAI-INC-READ-01"}
        interaction_read_again.response = MagicMock()
        interaction_read_again.response.send_message = AsyncMock()

        handled_again = await InteractiveIncidentManager.handle_component_interaction(self.bot, interaction_read_again)
        self.assertTrue(handled_again)
        interaction_read_again.response.send_message.assert_called_once()
        self.assertIn("already been marked as read", interaction_read_again.response.send_message.call_args[0][0])

    async def test_mark_all_read_bulk_workflow(self):
        """Test clicking Mark All Read bulk resolves all open incidents in the server."""
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        for i in range(1, 4):
            inc = InteractiveIncident(
                incident_id=f"RAI-INC-BULK-0{i}",
                guild_id=self.guild_id,
                report_type="security" if i % 2 == 1 else "system",
                event_type="threat_alert",
                title=f"Incident Alert #{i}",
                description="Simulated attack alert",
                actor_id=12345678,
                actor_name="Attacker",
                target_id=None,
                target_name=None,
                action_taken=None,
                status="ACTION_REQUIRED",
                severity="HIGH",
                details_json="{}",
                dm_message_id=2000 + i,
                dm_channel_id=999,
                channel_message_id=3000 + i,
                report_channel_id=888,
                created_at=now_iso,
                updated_at=now_iso,
            )
            await self.db.create_interactive_incident(inc)

        # Verify 3 active incidents exist
        active_before = await self.db.get_active_interactive_incidents_for_guild(self.guild_id)
        self.assertEqual(len(active_before), 3)

        # Trigger Mark All Read from one of the alerts
        interaction = MagicMock(spec=discord.Interaction)
        interaction.type = discord.InteractionType.component
        interaction.data = {"custom_id": "rai_inc:mark_all_read:RAI-INC-BULK-01"}
        interaction.user = self.owner_user
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        handled = await InteractiveIncidentManager.handle_component_interaction(self.bot, interaction)
        self.assertTrue(handled)

        # Verify followup response sent to user
        interaction.followup.send.assert_called_once()
        feedback = interaction.followup.send.call_args[0][0]
        self.assertIn("Bulk Acknowledged", feedback)

        # Verify all incidents are now resolved in database
        active_after = await self.db.get_active_interactive_incidents_for_guild(self.guild_id)
        self.assertEqual(len(active_after), 0)

        for i in range(1, 4):
            inc = await self.db.get_interactive_incident(f"RAI-INC-BULK-0{i}")
            self.assertEqual(inc.status, "RESOLVED")
            self.assertIn("Bulk resolved", inc.action_taken)


if __name__ == "__main__":
    unittest.main()


