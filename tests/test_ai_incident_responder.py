"""
Unit tests for Rai AI Incident Analysis & One-Click DM Action Subsystem.
Verifies:
- AIIncidentAnalyzer threat classification & recommendations
- Contextual action buttons generation
- Interactive DM action execution (Delete, Lock, Timeout, Mark Safe)
- Privacy enforcement: Action buttons sent strictly in Owner DM, never in public logs.
"""

import asyncio
import datetime
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from utils.ai_incident_responder import AIIncidentAnalyzer, OwnerIncidentActionView
from cogs.logging import LoggingCog


class TestAIIncidentResponder(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot = MagicMock()
        self.bot.db = MagicMock()
        self.bot.db.get_logging_config = AsyncMock(return_value=MagicMock(general_channel_id=111))
        self.bot.db.get_founder_activity_dm = AsyncMock(return_value=True)
        self.bot.db.get_founder_dm_recipient = AsyncMock(return_value=1457380609641938981)

        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = 1457382179981099090
        self.guild.name = "RAI FAM"
        self.guild.owner_id = 1457380609641938981

        self.owner = MagicMock(spec=discord.User)
        self.owner.id = 1457380609641938981
        self.owner.bot = False
        self.owner.send = AsyncMock()
        self.bot.get_user.return_value = self.owner
        self.bot.get_guild.return_value = self.guild

        self.log_channel = MagicMock(spec=discord.TextChannel)
        self.log_channel.send = AsyncMock()
        self.guild.get_channel.return_value = self.log_channel

        self.cog = LoggingCog(self.bot)

    def test_ai_analyzer_channel_creation(self):
        bot_user = MagicMock(spec=discord.User)
        bot_user.name = "Rythm"
        bot_user.bot = True

        res = AIIncidentAnalyzer.analyze(
            event_type="channel_create",
            title="📁 Channel Created",
            description="Channel #backup-log created",
            actor=bot_user,
            target_name="backup-log",
        )
        self.assertEqual(res.threat_level, "🟡 MEDIUM")
        self.assertIn("Rythm", res.assessment)
        self.assertIn("delete_channel", res.actions)
        self.assertIn("lock_channel", res.actions)
        self.assertIn("mark_safe", res.actions)

    def test_ai_analyzer_unauthorized_mention(self):
        res = AIIncidentAnalyzer.analyze(
            event_type="everyone_mention",
            title="🚨 Unauthorized @everyone Mention",
            description="Spammer mentioned @everyone",
            target_name="Spammer",
        )
        self.assertEqual(res.threat_level, "🔴 CRITICAL")
        self.assertIn("ban_user", res.actions)
        self.assertIn("timeout_user", res.actions)

    def test_view_button_generation(self):
        analysis = AIIncidentAnalyzer.analyze(
            event_type="channel_create",
            title="📁 Channel Created",
            description="Channel created",
            target_name="test-channel",
        )
        view = OwnerIncidentActionView(
            bot=self.bot,
            guild_id=self.guild.id,
            target_id=123456789,
            target_name="test-channel",
            actor_id=None,
            event_type="channel_create",
            owner_id=self.owner.id,
            analysis=analysis,
        )
        button_labels = [item.label for item in view.children if isinstance(item, discord.ui.Button)]
        self.assertIn("Delete Channel", button_labels)
        self.assertIn("Lock Channel", button_labels)
        self.assertIn("Mark as Safe", button_labels)

    async def test_view_delete_channel_action(self):
        target_channel = MagicMock(spec=discord.TextChannel)
        target_channel.id = 555666777
        target_channel.name = "rogue-channel"
        target_channel.delete = AsyncMock()
        self.guild.get_channel.return_value = target_channel

        analysis = AIIncidentAnalyzer.analyze(
            event_type="channel_create",
            title="📁 Channel Created",
            description="",
            target_name="rogue-channel",
        )
        view = OwnerIncidentActionView(
            bot=self.bot,
            guild_id=self.guild.id,
            target_id=555666777,
            target_name="rogue-channel",
            actor_id=None,
            event_type="channel_create",
            owner_id=self.owner.id,
            analysis=analysis,
        )

        interaction = MagicMock(spec=discord.Interaction)
        interaction.user = self.owner
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()
        interaction.message = MagicMock()
        interaction.message.embeds = [discord.Embed(title="📁 Channel Created")]
        interaction.message.edit = AsyncMock()

        # Trigger delete channel
        await view._handle_delete_channel(interaction)

        target_channel.delete.assert_called_once()
        interaction.message.edit.assert_called_once()
        edited_embed = interaction.message.edit.call_args.kwargs["embed"]
        self.assertTrue(any("Founder Action Taken" in f.name for f in edited_embed.fields))

    async def test_dm_gets_ai_and_buttons_while_log_channel_gets_clean_embed(self):
        channel = MagicMock(spec=discord.TextChannel)
        channel.guild = self.guild
        channel.name = "test-log"
        channel.mention = "<#999>"
        channel.id = 999

        # Trigger on_guild_channel_create
        await self.cog.on_guild_channel_create(channel)

        # 1. Log channel received clean embed WITHOUT view
        self.log_channel.send.assert_called_once()
        log_kwargs = self.log_channel.send.call_args.kwargs
        self.assertNotIn("view", log_kwargs)
        self.assertEqual(log_kwargs["embed"].title, "📁 Channel Created")

        # 2. Founder DM received enriched embed WITH AI analysis AND OwnerIncidentActionView
        self.owner.send.assert_called_once()
        dm_kwargs = self.owner.send.call_args.kwargs
        self.assertIn("view", dm_kwargs)
        self.assertIsInstance(dm_kwargs["view"], OwnerIncidentActionView)

        dm_embed = dm_kwargs["embed"]
        field_names = [f.name for f in dm_embed.fields]
        self.assertIn("🧠 AI Incident Triage", field_names)

    def test_view_mark_all_read_button_generation(self):
        analysis = AIIncidentAnalyzer.analyze(
            event_type="channel_delete",
            title="📁 Channel Deleted",
            description="Channel deleted",
            target_name="casual-gaming",
        )
        # With pending_count = 5
        view = OwnerIncidentActionView(
            bot=self.bot,
            guild_id=self.guild.id,
            target_id=None,
            target_name="casual-gaming",
            actor_id=None,
            event_type="channel_delete",
            owner_id=self.owner.id,
            analysis=analysis,
            pending_count=5,
        )
        button_labels = [item.label for item in view.children if isinstance(item, discord.ui.Button)]
        self.assertIn("Mark All as Read (5)", button_labels)
        self.assertIn("Mark as Safe", button_labels)

    async def test_handle_mark_all_read_execution(self):
        from utils.ai_incident_responder import IncidentAlertTracker
        IncidentAlertTracker.reset()

        # Mock tracked messages
        mock_msg1 = MagicMock(spec=discord.Message)
        mock_msg1.id = 11111
        IncidentAlertTracker.add_alert(self.owner.id, mock_msg1)

        analysis = AIIncidentAnalyzer.analyze(
            event_type="channel_delete",
            title="📁 Channel Deleted",
            description="",
            target_name="casual-gaming",
        )
        view = OwnerIncidentActionView(
            bot=self.bot,
            guild_id=self.guild.id,
            target_id=None,
            target_name="casual-gaming",
            actor_id=None,
            event_type="channel_delete",
            owner_id=self.owner.id,
            analysis=analysis,
            pending_count=2,
        )

        interaction = MagicMock(spec=discord.Interaction)
        interaction.user = self.owner
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()
        interaction.message = MagicMock()
        interaction.message.id = 22222
        interaction.message.embeds = [discord.Embed(title="📁 Channel Deleted")]
        interaction.message.edit = AsyncMock()
        interaction.message.delete = AsyncMock()

        # Mock channel history
        mock_old_msg = MagicMock(spec=discord.Message)
        mock_old_msg.id = 11111
        mock_old_msg.author = self.bot.user
        mock_old_msg.delete = AsyncMock()

        async def mock_history(limit=75):
            yield mock_old_msg

        interaction.channel = MagicMock()
        interaction.channel.history = mock_history

        await view._handle_mark_all_read(interaction)

        # Triggering message edited to safe
        interaction.message.edit.assert_called_once()
        # Older message deleted
        mock_old_msg.delete.assert_called_once()
        # Triggering message autodeleted
        interaction.message.delete.assert_called_once()


if __name__ == "__main__":
    unittest.main()
