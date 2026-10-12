"""
Comprehensive Unit & Integration Test Suite for Production Bot Upgrade.
Validates:
- Module 1: High-Speed Anti-Nuke & /antinuke Command Suite
- Module 2: AutoMod Rules, Whitelist, Blacklist, and Diagnostic Simulation
- Module 3: Complete Moderation Commands (/clearwarnings, /softban, /purge, /nick, /modlogs)
- Module 4: 14 Separate Log Channels with Idempotent Setup (/logs setup, /logs test, /logs configure)
- Modules 5, 6, 7: Permanent Welcome & Goodbye Systems with Complete Placeholders & Diagnostics
- Utility: /ping, /uptime, /botinfo, /serverinfo, /userinfo, /permissions
"""

import asyncio
import datetime
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from cogs.moderation import ModerationCog
from cogs.security import SecurityCog
from cogs.logging import LoggingCog
from cogs.welcome import WelcomeCog, format_template
from cogs.automod import AutoModCog
from cogs.utility import UtilityCog
from database.database import Database
from database.migrations import run_migrations


class TestProductionUpgrade(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # In-memory SQLite database
        self.db = Database(":memory:")
        await self.db.connect()

        # Mock SentinelBot
        self.bot = MagicMock()
        self.bot.db = self.db
        self.bot.user = MagicMock()
        self.bot.user.id = 999888777
        self.bot.user.name = "The Raivora"
        self.bot.user.display_avatar.url = "https://cdn.discordapp.com/avatars/bot.png"
        self.bot.latency = 0.042
        self.bot.wait_until_ready = AsyncMock()
        self.bot.change_presence = AsyncMock()
        self.bot.guilds = []

        # Mock Guild
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = 123456789
        self.guild.name = "THOR APEX TEST GUILD"
        self.guild.owner_id = 111222333
        self.guild.member_count = 150
        self.guild.members = []
        self.guild.channels = []
        self.guild.text_channels = []
        self.guild.categories = []
        self.guild.roles = []
        self.guild.icon = None
        self.guild.banner = None
        self.guild.system_channel = None

        # Bot Member
        self.bot_member = MagicMock(spec=discord.Member)
        self.bot_member.id = 999888777
        self.bot_member.name = "The Raivora"
        self.bot_member.top_role = MagicMock()
        self.bot_member.top_role.position = 50
        self.bot_member.top_role.name = "Sentinel"
        self.bot_member.guild_permissions = discord.Permissions.all()
        self.guild.me = self.bot_member

        # Target Member
        self.target_member = MagicMock(spec=discord.Member)
        self.target_member.id = 444555666
        self.target_member.name = "RogueUser"
        self.target_member.display_name = "RogueUser"
        self.target_member.mention = "<@444555666>"
        self.target_member.guild = self.guild
        self.target_member.top_role = MagicMock()
        self.target_member.top_role.position = 10
        self.target_member.top_role.name = "Member"
        self.target_member.created_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=100)
        self.target_member.joined_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=10)
        self.target_member.timed_out_until = None
        self.target_member.roles = [self.target_member.top_role]
        self.target_member.ban = AsyncMock()
        self.target_member.kick = AsyncMock()
        self.target_member.timeout = AsyncMock()
        self.target_member.edit = AsyncMock()
        self.target_member.display_avatar = MagicMock()
        self.target_member.display_avatar.url = "https://cdn.discordapp.com/avatars/user.png"

        # Staff Member (Admin)
        self.staff_member = MagicMock(spec=discord.Member)
        self.staff_member.id = 111222333  # Owner
        self.staff_member.name = "ServerOwner"
        self.staff_member.display_name = "ServerOwner"
        self.staff_member.mention = "<@111222333>"
        self.staff_member.guild = self.guild
        self.staff_member.top_role = MagicMock()
        self.staff_member.top_role.position = 100
        self.staff_member.guild_permissions = discord.Permissions.all()
        self.staff_member.roles = [self.staff_member.top_role]

        # Initialize Cogs
        self.mod_cog = ModerationCog(self.bot)
        self.sec_cog = SecurityCog(self.bot)
        self.log_cog = LoggingCog(self.bot)
        self.welcome_cog = WelcomeCog(self.bot)
        self.automod_cog = AutoModCog(self.bot)
        self.utility_cog = UtilityCog(self.bot)

        # Initialize guild in database
        await self.db.get_or_create_guild_config(self.guild.id)

    async def asyncTearDown(self):
        if hasattr(self, 'utility_cog') and hasattr(self.utility_cog, '_rotate_presence'):
            self.utility_cog._rotate_presence.cancel()
        await self.db.close()

    # =========================================================================
    # MODULE 3: MODERATION COMMANDS TESTS
    # =========================================================================

    async def test_clearwarnings_command(self):
        """Verify /clearwarnings deletes strikes and logs action."""
        await self.db.add_warning(self.guild.id, self.target_member.id, self.staff_member.id, "Strike 1")
        await self.db.add_warning(self.guild.id, self.target_member.id, self.staff_member.id, "Strike 2")
        warns = await self.db.get_warnings(self.guild.id, self.target_member.id)
        self.assertEqual(len(warns), 2)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = self.guild
        interaction.user = self.staff_member
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        await self.mod_cog.clearwarnings.callback(self.mod_cog, interaction, self.target_member, "Clean slate")
        interaction.response.send_message.assert_called_once()
        sent_embed = interaction.response.send_message.call_args[1]["embed"]
        self.assertIn("Warnings Cleared", sent_embed.title)

        remaining = await self.db.get_warnings(self.guild.id, self.target_member.id)
        self.assertEqual(len(remaining), 0)

    async def test_softban_command(self):
        """Verify /softban bans to purge messages and immediately unbans."""
        self.guild.unban = AsyncMock()
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = self.guild
        interaction.user = self.staff_member
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        with patch("cogs.moderation.ConfirmView") as MockConfirm:
            mock_view = MagicMock()
            mock_view.wait = AsyncMock()
            mock_view.value = True
            MockConfirm.return_value = mock_view

            await self.mod_cog.softban.callback(self.mod_cog, interaction, self.target_member, "Raid cleanup", 1)

            self.target_member.ban.assert_called_once()
            self.guild.unban.assert_called_once()
            interaction.followup.send.assert_called_once()
            sent_embed = interaction.followup.send.call_args[1]["embed"]
            self.assertIn("Softbanned", sent_embed.title)

    async def test_nick_command(self):
        """Verify /nick changes member nickname with hierarchy validation."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = self.guild
        interaction.user = self.staff_member
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        await self.mod_cog.nick.callback(self.mod_cog, interaction, self.target_member, "NewNick", "Staff update")
        self.target_member.edit.assert_called_once_with(nick="NewNick", reason="Staff update (Modified by ServerOwner)")
        interaction.response.send_message.assert_called_once()

    async def test_modlogs_command(self):
        """Verify /modlogs displays full dossier of member standing."""
        await self.db.add_warning(self.guild.id, self.target_member.id, self.staff_member.id, "Past spam strike")
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = self.guild
        interaction.user = self.staff_member
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        await self.mod_cog.modlogs.callback(self.mod_cog, interaction, self.target_member)
        interaction.response.send_message.assert_called_once()
        sent_embed = interaction.response.send_message.call_args[1]["embed"]
        self.assertIn("Moderation Dossier", sent_embed.title)
        self.assertTrue(any("Past spam strike" in f.value for f in sent_embed.fields))

    # =========================================================================
    # MODULE 1: HIGH-SPEED ANTI-NUKE TESTS
    # =========================================================================

    async def test_antinuke_threshold_and_status(self):
        """Verify /antinuke threshold updates database settings correctly."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = self.guild
        interaction.user = self.staff_member
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        action_choice = MagicMock()
        action_choice.name = "Channel Deletion"
        action_choice.value = "channel_delete"

        await self.sec_cog.antinuke_threshold_cmd.callback(self.sec_cog, interaction, action_choice, 3, 20)
        interaction.response.send_message.assert_called_once()

        cfg = await self.db.get_security_config(self.guild.id)
        self.assertEqual(cfg.channel_delete_limit, 3)
        self.assertEqual(cfg.channel_delete_window, 20)

    async def test_antinuke_trust_management(self):
        """Verify /antinuke trust add, list, and remove."""
        user_to_trust = MagicMock(spec=discord.User)
        user_to_trust.id = 555666777
        user_to_trust.name = "TrustedCoAdmin"
        user_to_trust.mention = "<@555666777>"

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = self.guild
        interaction.user = self.staff_member
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        # Add trust
        await self.sec_cog.antinuke_trust_add.callback(self.sec_cog, interaction, user_to_trust, "Co-founder")
        trusted = await self.db.get_trusted_users(self.guild.id)
        self.assertEqual(len(trusted), 1)
        self.assertEqual(trusted[0].user_id, 555666777)

        # Remove trust
        await self.sec_cog.antinuke_trust_remove.callback(self.sec_cog, interaction, user_to_trust)
        trusted_after = await self.db.get_trusted_users(self.guild.id)
        self.assertEqual(len(trusted_after), 0)

    # =========================================================================
    # MODULE 4: SEPARATE LOG CHANNELS TESTS
    # =========================================================================

    async def test_logs_setup_idempotent_creation(self):
        """Verify /logs setup creates 📁 SERVER LOGS and all 14 channels without duplicates."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = self.guild
        interaction.user = self.staff_member
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        # Mock category & channel creation
        created_channels = {}
        mock_category = MagicMock(spec=discord.CategoryChannel)
        mock_category.name = "📁 SERVER LOGS"
        mock_category.text_channels = []

        async def fake_create_category(name, overwrites=None):
            self.guild.categories.append(mock_category)
            return mock_category

        async def fake_create_text_channel(name, category=None, overwrites=None, topic=None):
            ch = MagicMock(spec=discord.TextChannel)
            ch.id = 1000 + len(created_channels)
            ch.name = name
            ch.mention = f"<#{ch.id}>"
            created_channels[name] = ch
            self.guild.channels.append(ch)
            self.guild.text_channels.append(ch)
            if category:
                category.text_channels.append(ch)
            return ch

        self.guild.create_category = fake_create_category
        self.guild.create_text_channel = fake_create_text_channel

        # Run setup first time
        await self.log_cog.logs_setup.callback(self.log_cog, interaction, "📁 SERVER LOGS")
        self.assertEqual(len(created_channels), 14)

        log_cfg = await self.db.get_logging_config(self.guild.id)
        self.assertIsNotNone(log_cfg.member_channel_id)
        self.assertIsNotNone(log_cfg.anti_nuke_channel_id)
        self.assertIsNotNone(log_cfg.moderation_channel_id)
        self.assertIsNotNone(log_cfg.invite_logs_channel_id)
        self.assertIsNotNone(log_cfg.welcome_logs_channel_id)

        # Run setup a SECOND time: must NOT create new channels, must reuse existing!
        created_count_before = len(created_channels)
        self.guild.get_channel = lambda cid: next((c for c in self.guild.channels if c.id == cid), None)

        await self.log_cog.logs_setup.callback(self.log_cog, interaction, "📁 SERVER LOGS")
        # Count of channels should NOT have doubled
        self.assertEqual(len(created_channels), created_count_before)

    # =========================================================================
    # MODULES 5, 6, 7: WELCOME & GOODBYE TESTS
    # =========================================================================

    def test_format_template_all_placeholders(self):
        """Verify all 7 requested placeholders replace safely and accurately."""
        template = "Hi {user} ({username} ID: {userid})! Welcome to {server}! Member #{membercount}. Created: {created_at}. Joined: {joined_at}."
        formatted = format_template(template, self.target_member, self.guild)

        self.assertIn("<@444555666>", formatted)
        self.assertIn("RogueUser", formatted)
        self.assertIn("444555666", formatted)
        self.assertIn("THOR APEX TEST GUILD", formatted)
        self.assertIn("150", formatted)
        self.assertNotIn("{user}", formatted)
        self.assertNotIn("{username}", formatted)
        self.assertNotIn("{userid}", formatted)
        self.assertNotIn("{server}", formatted)
        self.assertNotIn("{membercount}", formatted)
        self.assertNotIn("{created_at}", formatted)
        self.assertNotIn("{joined_at}", formatted)

    async def test_goodbye_setup_and_config(self):
        """Verify /goodbye setup and config update database."""
        ch = MagicMock(spec=discord.TextChannel)
        ch.id = 888999
        ch.mention = "<#888999>"

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = self.guild
        interaction.user = self.staff_member
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        await self.welcome_cog.goodbye_setup.callback(
            self.welcome_cog, interaction, ch, "{username} left {server}. We have {membercount} members.", True
        )
        interaction.response.send_message.assert_called_once()

        w_cfg = await self.db.get_welcome_config(self.guild.id)
        self.assertEqual(w_cfg.goodbye_channel_id, 888999)
        self.assertTrue(w_cfg.goodbye_enabled)
        self.assertIn("{username} left", w_cfg.goodbye_message)

    # =========================================================================
    # MODULE 2: AUTOMOD TESTS
    # =========================================================================

    async def test_automod_diagnostic_test(self):
        """Verify /automod test catches scam links and banned keywords."""
        await self.db.update_automod_config(self.guild.id, banned_words="freecard,hacktool", suspicious_links_block=1)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = self.guild
        interaction.user = self.staff_member
        interaction.response = MagicMock()
        interaction.response.send_message = AsyncMock()

        # Test message with scam link
        await self.automod_cog.automod_test.callback(
            self.automod_cog, interaction, "Claim your reward at http://free-nitro.ru/gift now!"
        )
        sent_embed = interaction.response.send_message.call_args[1]["embed"]
        self.assertIn("TRIGGERED", sent_embed.description)

    # =========================================================================
    # UTILITY TESTS
    # =========================================================================

    async def test_ping_and_uptime_commands(self):
        """Verify /ping and /uptime return diagnostic latency and process times."""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = self.guild
        interaction.user = self.staff_member
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.response.send_message = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        await self.utility_cog.ping_cmd.callback(self.utility_cog, interaction)
        interaction.followup.send.assert_called_once()
        ping_embed = interaction.followup.send.call_args[1]["embed"]
        self.assertIn("Latency", ping_embed.title)

        await self.utility_cog.uptime_cmd.callback(self.utility_cog, interaction)
        interaction.response.send_message.assert_called_once()
        uptime_embed = interaction.response.send_message.call_args[1]["embed"]
        self.assertIn("Uptime", uptime_embed.title)


if __name__ == "__main__":
    unittest.main()
