"""
Unit and integration tests for OwnerReporter dual delivery, confidentiality, routing, and auto-repair.
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import discord

from utils.owner_reporter import OwnerReporter, OWNER_ID, BOT_ID, ReportDeduplicator, IncidentAggregator, generate_incident_id


class TestOwnerReporter(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        ReportDeduplicator.reset()

    async def test_embed_formatting(self):
        """Verify report embeds contain event, target, reason, action, severity, and incident ID."""
        fake_user = MagicMock(spec=discord.Member)
        fake_user.mention = "<@12345>"
        fake_user.name = "TestBadUser"
        fake_user.id = 12345

        embed = OwnerReporter._create_report_embed(
            title="🚨 Security Alert",
            color=0xED4245,
            event="Phishing Attack Intercepted",
            user=fake_user,
            reason="Malicious token logger link",
            action_taken="24h timeout applied and message deleted",
            severity="HIGH",
            details={"Channel": "<#9999>", "Threat Engine": "Rai Sentinel"},
            incident_id="RAI-INC-999001",
        )

        self.assertEqual(embed.title, "🚨 Security Alert")
        field_names = [f.name for f in embed.fields]
        self.assertIn("📌 Event / Action", field_names)
        self.assertIn("👤 Target / User", field_names)
        self.assertIn("⚡ Severity", field_names)
        self.assertIn("🆔 Incident ID", field_names)
        self.assertIn("📝 Reason / Trigger", field_names)
        self.assertIn("🛡️ Action Taken / Result", field_names)
        self.assertIn("Channel", field_names)
        self.assertIn("Threat Engine", field_names)
        self.assertIn("RAI-INC-999001", embed.footer.text)

    async def test_dual_delivery_both_succeed(self):
        """Verify report is delivered to BOTH Owner DM AND the private server report channel."""
        bot = MagicMock()
        guild = MagicMock(spec=discord.Guild)
        guild.id = 112233
        guild.name = "Test Guild"
        guild.owner_id = 998877

        # Owner mock
        owner_user = MagicMock(spec=discord.User)
        owner_user.bot = False
        owner_user.send = AsyncMock()
        bot.get_user.return_value = owner_user

        # Report channel mock
        report_channel = MagicMock(spec=discord.TextChannel)
        report_channel.id = 554433
        report_channel.name = "security-report"
        report_channel.send = AsyncMock()
        guild.get_channel.return_value = report_channel

        # DB config mock
        cfg = MagicMock()
        cfg.security_report_id = 554433
        cfg.auto_repair = True
        bot.db.get_owner_reports_config = AsyncMock(return_value=cfg)

        embed = discord.Embed(title="Dual Test")
        dm_ok, ch_ok = await OwnerReporter._dispatch_dual_report_async(
            bot=bot,
            guild_id=guild.id,
            channel_key="security_report_id",
            embed=embed,
            incident_id="RAI-INC-123456",
            guild=guild,
            bypass_dedup=True,
            force_dm=True,
        )

        self.assertTrue(dm_ok)
        self.assertTrue(ch_ok)
        owner_user.send.assert_awaited_once_with(embed=embed)
        report_channel.send.assert_awaited_once_with(embed=embed)

    async def test_dual_delivery_dm_fails_channel_still_delivered(self):
        """Verify failure isolation: If DM fails, channel delivery still succeeds."""
        bot = MagicMock()
        guild = MagicMock(spec=discord.Guild)
        guild.id = 112233
        guild.name = "Test Guild"
        guild.owner_id = 998877

        # Owner DM fails (e.g. DMs closed)
        owner_user = MagicMock(spec=discord.User)
        owner_user.bot = False
        owner_user.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "DMs closed"))
        bot.get_user.return_value = owner_user

        # Report channel succeeds
        report_channel = MagicMock(spec=discord.TextChannel)
        report_channel.id = 554433
        report_channel.name = "security-report"
        report_channel.send = AsyncMock()
        guild.get_channel.return_value = report_channel

        cfg = MagicMock()
        cfg.security_report_id = 554433
        cfg.auto_repair = True
        bot.db.get_owner_reports_config = AsyncMock(return_value=cfg)

        embed = discord.Embed(title="DM Fail Test")
        dm_ok, ch_ok = await OwnerReporter._dispatch_dual_report_async(
            bot=bot,
            guild_id=guild.id,
            channel_key="security_report_id",
            embed=embed,
            incident_id="RAI-INC-DMFAIL",
            guild=guild,
            bypass_dedup=True,
            force_dm=True,
        )

        self.assertFalse(dm_ok)
        self.assertTrue(ch_ok)
        report_channel.send.assert_awaited_once_with(embed=embed)

    async def test_security_report_suppresses_owner_dm_by_default_when_channel_succeeds(self):
        """Verify that security reports default to staying in server channel, suppressing owner DM."""
        bot = MagicMock()
        guild = MagicMock(spec=discord.Guild)
        guild.id = 112233
        guild.name = "Test Guild"
        guild.owner_id = 998877

        owner_user = MagicMock(spec=discord.User)
        owner_user.bot = False
        owner_user.send = AsyncMock()
        bot.get_user.return_value = owner_user

        report_channel = MagicMock(spec=discord.TextChannel)
        report_channel.id = 554433
        report_channel.name = "security-report"
        report_channel.send = AsyncMock()
        guild.get_channel.return_value = report_channel

        cfg = MagicMock()
        cfg.security_report_id = 554433
        cfg.auto_repair = True
        bot.db.get_owner_reports_config = AsyncMock(return_value=cfg)

        embed = discord.Embed(title="Security Event")
        dm_ok, ch_ok = await OwnerReporter._dispatch_dual_report_async(
            bot=bot,
            guild_id=guild.id,
            channel_key="security_report_id",
            embed=embed,
            incident_id="RAI-INC-SEC-NODM",
            guild=guild,
            bypass_dedup=True,
        )

        self.assertFalse(dm_ok)
        self.assertTrue(ch_ok)
        report_channel.send.assert_awaited_once_with(embed=embed)
        owner_user.send.assert_not_called()

    async def test_dual_delivery_channel_fails_dm_still_delivered(self):
        """Verify failure isolation: If Channel fails, DM delivery still succeeds."""
        bot = MagicMock()
        guild = MagicMock(spec=discord.Guild)
        guild.id = 112233
        guild.name = "Test Guild"
        guild.owner_id = 998877

        # Owner DM succeeds
        owner_user = MagicMock(spec=discord.User)
        owner_user.bot = False
        owner_user.send = AsyncMock()
        bot.get_user.return_value = owner_user

        # Report channel fails
        report_channel = MagicMock(spec=discord.TextChannel)
        report_channel.id = 554433
        report_channel.name = "security-report"
        report_channel.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "Missing Permissions"))
        guild.get_channel.return_value = report_channel

        cfg = MagicMock()
        cfg.security_report_id = 554433
        cfg.auto_repair = False
        bot.db.get_owner_reports_config = AsyncMock(return_value=cfg)

        embed = discord.Embed(title="Channel Fail Test")
        dm_ok, ch_ok = await OwnerReporter._dispatch_dual_report_async(
            bot=bot,
            guild_id=guild.id,
            channel_key="security_report_id",
            embed=embed,
            incident_id="RAI-INC-CHFAIL",
            guild=guild,
            bypass_dedup=True,
        )

        self.assertTrue(dm_ok)
        self.assertFalse(ch_ok)
        owner_user.send.assert_awaited_once_with(embed=embed)

    async def test_deduplication_suppresses_redundant_dispatches(self):
        """Verify duplicate reports within sliding window are caught and suppressed."""
        bot = MagicMock()
        guild = MagicMock(spec=discord.Guild)
        guild.id = 112233
        guild.owner_id = 998877

        owner_user = MagicMock(spec=discord.User)
        owner_user.bot = False
        owner_user.send = AsyncMock()
        bot.get_user.return_value = owner_user

        report_channel = MagicMock(spec=discord.TextChannel)
        report_channel.send = AsyncMock()
        guild.get_channel.return_value = report_channel

        cfg = MagicMock()
        cfg.security_report_id = 554433
        bot.db.get_owner_reports_config = AsyncMock(return_value=cfg)

        embed = discord.Embed(title="Identical Report")

        # First dispatch should succeed
        dm1, ch1 = await OwnerReporter._dispatch_dual_report_async(
            bot=bot,
            guild_id=guild.id,
            channel_key="security_report_id",
            embed=embed,
            incident_id="RAI-INC-DEDUP-01",
            guild=guild,
            bypass_dedup=False,
            force_dm=True,
        )
        self.assertTrue(dm1)
        self.assertEqual(owner_user.send.await_count, 1)

        # Immediate second dispatch with identical incident ID should be suppressed by deduplicator
        dm2, ch2 = await OwnerReporter._dispatch_dual_report_async(
            bot=bot,
            guild_id=guild.id,
            channel_key="security_report_id",
            embed=embed,
            incident_id="RAI-INC-DEDUP-01",
            guild=guild,
            bypass_dedup=False,
            force_dm=True,
        )
        self.assertTrue(dm2)
        # Count should remain 1 (suppressed)
        self.assertEqual(owner_user.send.await_count, 1)

    async def test_strict_private_channel_overwrites(self):
        """Verify strict permission matrix: Only current server owner and Rai have view access."""
        bot = MagicMock()
        bot.user.id = 1554732669072445532

        guild = MagicMock(spec=discord.Guild)
        guild.owner_id = 445566
        guild.default_role = MagicMock()
        guild.default_role.id = 1111

        mod_role = MagicMock()
        mod_role.id = 2222
        admin_role = MagicMock()
        admin_role.id = 3333
        guild.roles = [guild.default_role, mod_role, admin_role]

        owner_member = MagicMock(spec=discord.Member)
        owner_member.id = 445566
        guild.get_member.side_effect = lambda uid: owner_member if uid == 445566 else None
        guild.owner = owner_member
        guild.me = MagicMock(spec=discord.Member)

        overwrites = OwnerReporter._build_strict_overwrites(bot, guild)

        # 1. @everyone must be completely denied
        self.assertIn(guild.default_role, overwrites)
        self.assertFalse(overwrites[guild.default_role].view_channel)
        self.assertFalse(overwrites[guild.default_role].read_messages)
        self.assertFalse(overwrites[guild.default_role].send_messages)

        # 2. Other roles (mods, staff, admins) must be explicitly denied
        self.assertIn(mod_role, overwrites)
        self.assertFalse(overwrites[mod_role].view_channel)
        self.assertIn(admin_role, overwrites)
        self.assertFalse(overwrites[admin_role].view_channel)

        # 3. Dynamic Server Owner must have full view and send permissions
        self.assertIn(owner_member, overwrites)
        self.assertTrue(overwrites[owner_member].view_channel)
        self.assertTrue(overwrites[owner_member].send_messages)

        # 4. Rai Bot must have view, send, embed, and attach permissions
        self.assertIn(guild.me, overwrites)
        self.assertTrue(overwrites[guild.me].view_channel)
        self.assertTrue(overwrites[guild.me].embed_links)

    async def test_all_6_router_methods(self):
        """Verify all 6 specialized routers dispatch dual reports to the correct channel keys."""
        bot = MagicMock()
        guild_id = 998811

        with patch.object(OwnerReporter, "dispatch_report") as mock_dispatch:
            # 1. Security report -> security_report_id
            OwnerReporter.send_security_report(bot, guild_id, "Nuke Attack")
            mock_dispatch.assert_called_with(bot, guild_id, "security_report_id", unittest.mock.ANY, incident_id=unittest.mock.ANY)

            # 2. Moderation report -> mod_report_id
            OwnerReporter.send_mod_report(bot, guild_id, "Member Banned")
            mock_dispatch.assert_called_with(bot, guild_id, "mod_report_id", unittest.mock.ANY, incident_id=unittest.mock.ANY)

            # 3. Music report -> music_report_id
            OwnerReporter.send_music_report(bot, guild_id, "Stream Corrupted")
            mock_dispatch.assert_called_with(bot, guild_id, "music_report_id", unittest.mock.ANY, incident_id=unittest.mock.ANY)

            # 4. Room report -> room_report_id
            OwnerReporter.send_room_report(bot, guild_id, "VC Created")
            mock_dispatch.assert_called_with(bot, guild_id, "room_report_id", unittest.mock.ANY, incident_id=unittest.mock.ANY)

            # 5. Bot report -> bot_report_id
            OwnerReporter.send_bot_report(bot, guild_id, "Config Synced")
            mock_dispatch.assert_called_with(bot, guild_id, "bot_report_id", unittest.mock.ANY, incident_id=unittest.mock.ANY)

            # 6. System report -> system_report_id
            OwnerReporter.send_system_report(bot, guild_id, "DB Vacuum")
            mock_dispatch.assert_called_with(bot, guild_id, "system_report_id", unittest.mock.ANY, incident_id=unittest.mock.ANY)

    async def test_routine_reports_delivered_to_channel_and_suppress_dms(self):
        """Verify that routine telemetry (system, bot, music, room, mod) routes to server channel and suppresses DMs."""
        bot = MagicMock()
        guild = MagicMock(spec=discord.Guild)
        guild.id = 112233
        guild.owner_id = 998877

        owner_user = MagicMock(spec=discord.User)
        owner_user.bot = False
        owner_user.send = AsyncMock()
        bot.get_user.return_value = owner_user

        report_channel = MagicMock(spec=discord.TextChannel)
        report_channel.id = 776655
        report_channel.name = "system-report"
        report_channel.send = AsyncMock()
        guild.get_channel.return_value = report_channel

        cfg = MagicMock()
        cfg.system_report_id = 776655
        cfg.auto_repair = True
        bot.db.get_owner_reports_config = AsyncMock(return_value=cfg)

        embed = discord.Embed(title="System Heartbeat")
        dm_ok, ch_ok = await OwnerReporter._dispatch_dual_report_async(
            bot=bot,
            guild_id=guild.id,
            channel_key="system_report_id",
            embed=embed,
            incident_id="RAI-INC-ROUTINE",
            guild=guild,
            bypass_dedup=True,
        )

        # Channel must succeed, and DM must be suppressed
        self.assertTrue(ch_ok)
        self.assertFalse(dm_ok)
        report_channel.send.assert_awaited_once_with(embed=embed)
        owner_user.send.assert_not_called()

    async def test_routine_report_falls_back_to_dm_if_channel_fails(self):
        """Verify that if server report channel fails for routine reports, it falls back to DM."""
        bot = MagicMock()
        guild = MagicMock(spec=discord.Guild)
        guild.id = 112233
        guild.owner_id = 998877

        owner_user = MagicMock(spec=discord.User)
        owner_user.bot = False
        owner_user.send = AsyncMock()
        bot.get_user.return_value = owner_user

        # Channel fails
        report_channel = MagicMock(spec=discord.TextChannel)
        report_channel.id = 776655
        report_channel.name = "system-report"
        report_channel.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "Channel missing"))
        guild.get_channel.return_value = report_channel

        cfg = MagicMock()
        cfg.system_report_id = 776655
        cfg.auto_repair = False
        bot.db.get_owner_reports_config = AsyncMock(return_value=cfg)

        embed = discord.Embed(title="System Vacuum Note")
        dm_ok, ch_ok = await OwnerReporter._dispatch_dual_report_async(
            bot=bot,
            guild_id=guild.id,
            channel_key="system_report_id",
            embed=embed,
            incident_id="RAI-INC-FALLBACK",
            guild=guild,
            bypass_dedup=True,
        )

        self.assertFalse(ch_ok)
        self.assertTrue(dm_ok)
        owner_user.send.assert_awaited_once_with(embed=embed)

    async def test_incident_aggregator_gathers_burst_details_and_reports_once(self):
        """Verify rapid repeated incident triggers are gathered and dispatched as ONE consolidated report."""
        bot = MagicMock()
        guild = MagicMock(spec=discord.Guild)
        guild.id = 887766
        guild.owner_id = 112233

        IncidentAggregator._debounce_seconds = 0.05
        dispatch_mock = AsyncMock(return_value=(True, True))

        # Event 1
        embed1 = discord.Embed(title="🚨 Security Alert: Mass User Mention Spam")
        embed1.add_field(name="📌 Event / Action", value="**Mass User Mention Spam**")
        embed1.add_field(name="👤 Target / User", value="<@4455> (Attacker | ID: 4455)")
        embed1.add_field(name="📝 Reason / Trigger", value="Mentions: 10 across 1 channels")
        embed1.add_field(name="🛡️ Action Taken / Result", value="Deleted 1 message")
        embed1.add_field(name="Total Mentions", value="10")
        embed1.add_field(name="Channels", value="1 affected (<#111>)")

        # Event 2 (same attacker, rapid burst)
        embed2 = discord.Embed(title="🚨 Security Alert: Mass User Mention Spam")
        embed2.add_field(name="📌 Event / Action", value="**Mass User Mention Spam**")
        embed2.add_field(name="👤 Target / User", value="<@4455> (Attacker | ID: 4455)")
        embed2.add_field(name="📝 Reason / Trigger", value="Mentions: 15 across 2 channels")
        embed2.add_field(name="🛡️ Action Taken / Result", value="Timed out (1h)")
        embed2.add_field(name="Total Mentions", value="15")
        embed2.add_field(name="Channels", value="2 affected (<#111>, <#222>)")

        await IncidentAggregator.aggregate_report(
            bot=bot,
            guild_id=guild.id,
            channel_key="security_report_id",
            embed=embed1,
            incident_id="RAI-INC-AGGR-01",
            guild=guild,
            dispatch_func=dispatch_mock,
        )

        await IncidentAggregator.aggregate_report(
            bot=bot,
            guild_id=guild.id,
            channel_key="security_report_id",
            embed=embed2,
            incident_id="RAI-INC-AGGR-01",
            guild=guild,
            dispatch_func=dispatch_mock,
        )

        # Allow debounce to fire
        import asyncio
        await asyncio.sleep(0.15)

        # Dispatch should be called EXACTLY ONCE
        self.assertEqual(dispatch_mock.await_count, 1)
        call_kwargs = dispatch_mock.call_args[1]
        dispatched_embed = call_kwargs["embed"]

        # Check aggregated details
        self.assertIn("Aggregated Summary", dispatched_embed.title)
        field_dict = {f.name: f.value for f in dispatched_embed.fields}
        self.assertIn("`2` events gathered", field_dict.get("📊 Incident Bursts", ""))
        # Combined mentions: 10 + 15 = 25
        self.assertEqual(field_dict.get("Total Mentions"), "25")
        # Both channels present
        self.assertIn("<#111>", field_dict.get("📍 Channels Affected", ""))
        self.assertIn("<#222>", field_dict.get("📍 Channels Affected", ""))

    async def test_delete_incident_messages_dual(self):
        """Verify delete_incident_messages removes both DM and report channel messages."""
        from utils.interactive_incidents import InteractiveIncidentManager
        from database.models import InteractiveIncident

        bot = MagicMock()
        dm_channel = MagicMock(spec=discord.DMChannel)
        dm_message = MagicMock(spec=discord.Message)
        dm_message.delete = AsyncMock()
        dm_channel.fetch_message = AsyncMock(return_value=dm_message)

        report_channel = MagicMock(spec=discord.TextChannel)
        ch_message = MagicMock(spec=discord.Message)
        ch_message.delete = AsyncMock()
        report_channel.fetch_message = AsyncMock(return_value=ch_message)

        bot.get_channel.side_effect = lambda cid: dm_channel if cid == 1010 else (report_channel if cid == 2020 else None)

        incident = InteractiveIncident(
            incident_id="RAI-INC-DEL-01",
            guild_id=123,
            report_type="security",
            event_type="Raid",
            title="Raid Alert",
            description="Details",
            status="RESOLVED",
            dm_channel_id=1010,
            dm_message_id=9001,
            report_channel_id=2020,
            channel_message_id=9002,
        )

        await InteractiveIncidentManager.delete_incident_messages(bot, incident)

        dm_message.delete.assert_awaited_once()
        ch_message.delete.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()

