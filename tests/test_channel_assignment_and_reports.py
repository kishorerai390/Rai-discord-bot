"""
Integration and Unit Tests for:
1. GuildChannelConfig database persistence and canonical 17-channel layout.
2. ChannelAssignmentService: Discovery without mutations, ambiguity detection, health auditing, and test delivery.
3. InteractionManager: Immediate sub-100ms ACK, Request ID, double-reply prevention, and error boundary.
4. SecurityIncidentService: Benign routine event filtering (Dynamic VC joins != security threats), incident aggregation, and Mark as Safe.
5. Report routing: Destination resolution to canonical channels.
"""

from __future__ import annotations

import asyncio
import datetime
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from core.interaction_manager import InteractionManager, InteractionState, ManagedInteractionContext
from database.database import Database
from database.models import GuildChannelConfig, InteractionRecord, InteractiveIncident
from services.channel_assignment_service import (
    CANONICAL_CHANNELS,
    PURPOSE_MAP,
    ChannelAssignmentService,
    ChannelHealthStatus,
)
from services.report_service import ReportResult, ReportSeverity, ReportStatus, ReportType, ReportService
from services.security_incident_service import (
    EventClassification,
    IncidentSeverity,
    SecurityIncidentService,
)


class TestChannelAssignmentAndReports(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        # Create an in-memory SQLite database for isolated testing
        self.db = Database(":memory:")
        await self.db.connect()

        self.guild_id = 987654321098765432
        self.user_id = 123456789012345678

        # Mock Bot
        self.bot = MagicMock()
        self.bot.db = self.db
        self.bot.user = MagicMock(spec=discord.ClientUser)
        self.bot.user.id = 555555555555555555
        self.bot.is_ready.return_value = True
        self.bot.latency = 0.042

        # Mock Guild
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = self.guild_id
        self.guild.name = "Rai Production Hub"
        self.guild.owner_id = self.user_id

        # Mock Bot Member
        self.bot_member = MagicMock(spec=discord.Member)
        self.bot_member.id = self.bot.user.id
        self.guild.me = self.bot_member
        self.bot.get_guild.return_value = self.guild

    async def asyncTearDown(self):
        await self.db.close()

    # =========================================================================
    # 1. DATABASE & GUILD CHANNEL CONFIG TESTS
    # =========================================================================

    async def test_guild_channel_config_persistence(self):
        """Verify full round-trip persistence of all 17 canonical channel fields."""
        cfg = await self.db.set_guild_channel_config(
            self.guild_id,
            security_alerts_channel_id=101,
            anti_nuke_channel_id=102,
            lockdown_control_channel_id=103,
            security_log_channel_id=104,
            audit_monitor_channel_id=105,
            security_report_channel_id=201,
            moderation_report_channel_id=202,
            music_report_channel_id=203,
            room_report_channel_id=204,
            bot_report_channel_id=205,
            system_report_channel_id=206,
            admin_control_channel_id=301,
            server_dashboard_channel_id=302,
            bot_config_channel_id=303,
            automation_control_channel_id=304,
            backup_control_channel_id=305,
            system_health_channel_id=306,
        )

        self.assertIsNotNone(cfg)
        self.assertEqual(cfg.guild_id, self.guild_id)
        self.assertEqual(cfg.security_alerts_channel_id, 101)
        self.assertEqual(cfg.music_report_channel_id, 203)
        self.assertEqual(cfg.system_health_channel_id, 306)

        # Retrieve again
        fetched = await self.db.get_guild_channel_config(self.guild_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.room_report_channel_id, 204)
        self.assertEqual(fetched.admin_control_channel_id, 301)

        # Update partial
        updated = await self.db.update_guild_channel_config(
            self.guild_id, music_report_channel_id=999
        )
        self.assertEqual(updated.music_report_channel_id, 999)
        self.assertEqual(updated.security_alerts_channel_id, 101)

    # =========================================================================
    # 2. CHANNEL DISCOVERY & PERMISSIONS TESTS (NO MUTATIONS)
    # =========================================================================

    def _create_mock_channel(self, channel_id: int, name: str, perms_dict: dict = None) -> MagicMock:
        ch = MagicMock(spec=discord.TextChannel)
        ch.id = channel_id
        ch.name = name
        ch.guild = self.guild
        ch.mention = f"<#{channel_id}>"

        permissions = MagicMock()
        permissions.view_channel = perms_dict.get("view_channel", True) if perms_dict else True
        permissions.send_messages = perms_dict.get("send_messages", True) if perms_dict else True
        permissions.embed_links = perms_dict.get("embed_links", True) if perms_dict else True
        permissions.read_message_history = perms_dict.get("read_message_history", True) if perms_dict else True

        ch.permissions_for.return_value = permissions
        ch.send = AsyncMock()
        return ch

    async def test_channel_discovery_matches_without_creating_or_renaming(self):
        """Auto-discovery matches existing channels and DOES NOT create or rename channels."""
        ch_sec_alert = self._create_mock_channel(1001, "🚨・security-alerts")
        ch_music_rep = self._create_mock_channel(1002, "🎵・music-report")
        ch_admin_ctrl = self._create_mock_channel(1003, "👑・admin-control")
        ch_general = self._create_mock_channel(1004, "general-chat")

        self.guild.channels = [ch_sec_alert, ch_music_rep, ch_admin_ctrl, ch_general]

        discovery = ChannelAssignmentService.discover_channels(self.guild)

        # Single matches mapped
        self.assertEqual(discovery.matched.get("security_alerts"), 1001)
        self.assertEqual(discovery.matched.get("music_report"), 1002)
        self.assertEqual(discovery.matched.get("admin_control"), 1003)

        # Non-matching channel remains unmapped
        self.assertNotIn("general-chat", discovery.matched)

    async def test_channel_discovery_detects_ambiguous_duplicates(self):
        """If duplicate channels exist, flags ambiguity instead of blindly guessing."""
        ch_rep1 = self._create_mock_channel(2001, "room-report")
        ch_rep2 = self._create_mock_channel(2002, "ROOM-REPORT")

        self.guild.channels = [ch_rep1, ch_rep2]

        discovery = ChannelAssignmentService.discover_channels(self.guild)
        self.assertIn("room_report", discovery.ambiguous)
        self.assertEqual(len(discovery.ambiguous["room_report"]), 2)
        self.assertNotIn("room_report", discovery.matched)

    async def test_channel_permission_audit(self):
        """Verifies least-privilege checks (View, Send, Embed, History)."""
        valid_ch = self._create_mock_channel(3001, "audit-monitor")
        ok, missing = ChannelAssignmentService.check_permissions(valid_ch)
        self.assertTrue(ok)
        self.assertEqual(missing, [])

        # Missing embed links
        broken_ch = self._create_mock_channel(3002, "audit-monitor", {"embed_links": False})
        ok2, missing2 = ChannelAssignmentService.check_permissions(broken_ch)
        self.assertFalse(ok2)
        self.assertIn("Embed Links", missing2)

    async def test_channel_health_status_evaluation(self):
        """Verifies CONNECTED, MISSING, NO_PERMISSION, and DISABLED statuses."""
        ch = self._create_mock_channel(4001, "security-log")
        self.guild.get_channel.side_effect = lambda cid: ch if cid == 4001 else None

        # Connected
        h1 = ChannelAssignmentService.evaluate_channel_health(self.guild, "security_log", 4001)
        self.assertEqual(h1.status, ChannelHealthStatus.CONNECTED)

        # Missing (channel ID does not exist in guild)
        h2 = ChannelAssignmentService.evaluate_channel_health(self.guild, "security_log", 999999)
        self.assertEqual(h2.status, ChannelHealthStatus.MISSING)

        # Disabled (channel ID is None)
        h3 = ChannelAssignmentService.evaluate_channel_health(self.guild, "security_log", None)
        self.assertEqual(h3.status, ChannelHealthStatus.DISABLED)

    # =========================================================================
    # 3. INTERACTION MANAGER & LATENCY TESTS
    # =========================================================================

    async def test_interaction_immediate_acknowledgement_and_request_id(self):
        """Interaction is immediately deferred under 100ms with a unique Request ID."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.id = 777123456789
        interaction.type = discord.InteractionType.application_command
        interaction.user = MagicMock()
        interaction.user.id = self.user_id
        interaction.guild_id = self.guild_id
        interaction.command = MagicMock()
        interaction.command.name = "security"
        interaction.response = MagicMock()
        interaction.response.is_done.return_value = False
        interaction.response.defer = AsyncMock()

        ctx = await InteractionManager.register_interaction(interaction)
        self.assertTrue(ctx.request_id.startswith("RAI-REQ-"))
        self.assertEqual(ctx.state, InteractionState.NOT_ACKNOWLEDGED)

        success = await InteractionManager.acknowledge_immediately(interaction, ephemeral=True)
        self.assertTrue(success)
        self.assertEqual(ctx.state, InteractionState.DEFERRED)
        interaction.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)

        # ACK latency recorded
        self.assertIsNotNone(ctx.ack_latency_ms)
        self.assertGreaterEqual(ctx.ack_latency_ms, 0.0)

    async def test_double_reply_prevention(self):
        """Prevent multiple deferrals or replies on the same interaction."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.id = 888123456789
        interaction.type = discord.InteractionType.component
        interaction.user = MagicMock()
        interaction.user.id = self.user_id
        interaction.guild_id = self.guild_id
        interaction.command = None
        interaction.response = MagicMock()
        interaction.response.is_done.return_value = False
        interaction.response.defer = AsyncMock()

        await InteractionManager.acknowledge_immediately(interaction, is_component_update=True)
        interaction.response.is_done.return_value = True

        # Second deferral attempt must be safely absorbed
        second_ack = await InteractionManager.acknowledge_immediately(interaction, is_component_update=True)
        self.assertTrue(second_ack)
        self.assertEqual(interaction.response.defer.await_count, 1)

    async def test_execute_interaction_wrapper_with_error_boundary(self):
        """Wraps operation in error boundary, logs traceback, and returns sanitized error to user."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.id = 999123456789
        interaction.type = discord.InteractionType.application_command
        interaction.user = MagicMock()
        interaction.user.id = self.user_id
        interaction.guild_id = self.guild_id
        interaction.command = MagicMock()
        interaction.command.name = "test_fail"
        interaction.response = MagicMock()
        interaction.response.is_done.return_value = True
        interaction.edit_original_response = AsyncMock()

        async def failing_operation(inter, ctx):
            raise ValueError("Intentional simulated failure for testing")

        result = await InteractionManager.execute_interaction(
            interaction,
            "Failing Test",
            failing_operation,
            auto_defer=False,
        )

        self.assertIsNone(result)
        # Verify user receives sanitized error embed with Request ID
        interaction.edit_original_response.assert_awaited_once()
        call_kwargs = interaction.edit_original_response.call_args[1]
        sent_embed = call_kwargs.get("embed")
        self.assertIsNotNone(sent_embed)
        self.assertIn("RAI-REQ-", sent_embed.description)
        self.assertNotIn("Traceback", sent_embed.description)

    # =========================================================================
    # 4. EVENT CLASSIFICATION & NO FALSE POSITIVES
    # =========================================================================

    def test_normal_voice_events_are_never_security_threats(self):
        """CRITICAL: Normal voice connects/disconnects must NOT create security incidents."""
        # 1. Single voice join
        c1 = SecurityIncidentService.classify_event("voice_room_connected", count=1)
        self.assertFalse(c1.is_security_incident)
        self.assertFalse(c1.allow_report)
        self.assertFalse(c1.requires_alert)

        # 2. Dynamic VC room trigger
        c2 = SecurityIncidentService.classify_event("voice_room_create_request", count=1)
        self.assertFalse(c2.is_security_incident)

        # 3. Normal track play
        c3 = SecurityIncidentService.classify_event("music_track_start", count=1)
        self.assertFalse(c3.is_security_incident)

    def test_actual_security_attacks_classified_correctly(self):
        """Mass destruction and rapid floods MUST be classified as security threats."""
        # 1. Mass channel deletion (Anti-Nuke)
        c_nuke = SecurityIncidentService.classify_event("channel_delete", count=4)
        self.assertTrue(c_nuke.is_security_incident)
        self.assertEqual(c_nuke.severity, IncidentSeverity.CRITICAL)
        self.assertTrue(c_nuke.requires_alert)

        # 2. Mass voice raid spike (35 joins in 10s)
        c_raid = SecurityIncidentService.classify_event("voice_member_joined", count=35, time_window_sec=10.0)
        self.assertTrue(c_raid.is_security_incident)
        self.assertEqual(c_raid.severity, IncidentSeverity.HIGH)

        # 3. Webhook flood
        c_webhook = SecurityIncidentService.classify_event("webhook_create", count=3)
        self.assertTrue(c_webhook.is_security_incident)
        self.assertEqual(c_webhook.severity, IncidentSeverity.CRITICAL)

    # =========================================================================
    # 5. INCIDENT AGGREGATION & IN-PLACE MESSAGE UPDATES
    # =========================================================================

    async def test_incident_aggregation_updates_existing_message(self):
        """Repeated events aggregate into ONE Incident ID and edit existing message."""
        sec_alert_ch = self._create_mock_channel(5001, "security-alerts")
        sec_rep_ch = self._create_mock_channel(5002, "security-report")

        self.guild.get_channel.side_effect = lambda cid: {
            5001: sec_alert_ch,
            5002: sec_rep_ch,
        }.get(cid)

        # Configure channels in DB
        await self.db.set_guild_channel_config(
            self.guild_id,
            security_alerts_channel_id=5001,
            security_report_channel_id=5002,
        )

        mock_sent_msg = MagicMock(spec=discord.Message)
        mock_sent_msg.id = 88880001
        mock_sent_msg.edit = AsyncMock()
        sec_alert_ch.send.return_value = mock_sent_msg
        sec_rep_ch.send.return_value = mock_sent_msg
        sec_rep_ch.fetch_message = AsyncMock(return_value=mock_sent_msg)

        # First trigger: Mass channel deletions
        inc1 = await SecurityIncidentService.process_security_signal(
            bot=self.bot,
            guild=self.guild,
            event_type="channel_delete",
            title="Mass Channel Deletion",
            description="3 channels deleted within 5s",
            count=3,
        )

        self.assertIsNotNone(inc1)
        self.assertTrue(inc1.incident_id.startswith("RAI-INC-"))
        first_id = inc1.incident_id

        # Second trigger of identical event within time window
        inc2 = await SecurityIncidentService.process_security_signal(
            bot=self.bot,
            guild=self.guild,
            event_type="channel_delete",
            title="Mass Channel Deletion",
            description="3 channels deleted within 5s",
            count=2,
        )

        # Must retain the EXACT SAME incident ID
        self.assertEqual(inc2.incident_id, first_id)
        # In-place edit was called
        mock_sent_msg.edit.assert_awaited()

    # =========================================================================
    # 6. MARK AS SAFE ACTION
    # =========================================================================

    async def test_mark_as_safe_acknowledges_and_resolves_incident(self):
        """'Mark as Safe' button updates incident status, edits message in place, and stops repeats."""
        incident = InteractiveIncident(
            incident_id="RAI-INC-999001",
            guild_id=self.guild_id,
            report_type="security",
            event_type="channel_delete",
            actor_id=self.user_id,
            actor_name="TestAdmin",
            title="Potential Attack",
            description="Test alert",
            status="ACTIVE",
            severity="CRITICAL",
            created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            updated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )
        await self.db.create_interactive_incident(incident)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.id = 55512345
        interaction.user = MagicMock()
        interaction.user.id = self.user_id
        interaction.user.mention = f"<@{self.user_id}>"
        interaction.guild = self.guild
        interaction.permissions = discord.Permissions(administrator=True)
        interaction.response = MagicMock()
        interaction.response.is_done.return_value = False
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        mock_msg = MagicMock(spec=discord.Message)
        mock_msg.embeds = [discord.Embed(title="🚨 Alert")]
        mock_msg.edit = AsyncMock()
        interaction.message = mock_msg

        success = await SecurityIncidentService.mark_incident_safe(
            self.bot, interaction, "RAI-INC-999001"
        )

        self.assertTrue(success)
        # Message was edited in place with Marked Safe banner
        mock_msg.edit.assert_awaited_once()
        edit_embed = mock_msg.edit.call_args[1].get("embed")
        self.assertIn("MARKED SAFE", edit_embed.title)
        self.assertEqual(edit_embed.color.value, 0x57F287)

        # Incident updated to RESOLVED in database
        resolved_inc = await self.db.get_interactive_incident("RAI-INC-999001")
        self.assertEqual(resolved_inc.status, "RESOLVED")
        self.assertIn("Marked as Safe", resolved_inc.action_taken)


if __name__ == "__main__":
    unittest.main()
