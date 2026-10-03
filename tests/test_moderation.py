import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import discord

from cogs.moderation import ModerationCog
from utils.permissions import can_moderate, is_founder_or_owner


class TestModeration(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot = MagicMock()
        self.bot.db = MagicMock()
        self.cog = ModerationCog(self.bot)
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = 1457382179981099090
        self.guild.owner_id = 1457380609641938981  # Founder ID

        class MockRole:
            def __init__(self, name, position):
                self.name = name
                self.position = position
            def __ge__(self, other):
                return self.position >= other.position

        self.MockRole = MockRole

    def test_can_moderate_owner_disallowed(self):
        mod = MagicMock(spec=discord.Member)
        mod.id = 1111
        mod.guild = self.guild
        mod.top_role = self.MockRole("Moderator", 30)

        target = MagicMock(spec=discord.Member)
        target.id = self.guild.owner_id
        target.guild = self.guild
        target.top_role = self.MockRole("Founder", 41)

        bot_member = MagicMock(spec=discord.Member)
        bot_member.id = 9999
        bot_member.top_role = self.MockRole("The Raivora", 40)

        can_mod, err = can_moderate(mod, target, bot_member)
        self.assertFalse(can_mod)
        self.assertIn("server owner", err.lower())

    def test_can_moderate_bot_disallowed(self):
        mod = MagicMock(spec=discord.Member)
        mod.id = 1111
        mod.guild = self.guild
        mod.top_role = self.MockRole("Moderator", 30)

        bot_member = MagicMock(spec=discord.Member)
        bot_member.id = 9999
        bot_member.top_role = self.MockRole("The Raivora", 40)

        can_mod, err = can_moderate(mod, bot_member, bot_member)
        self.assertFalse(can_mod)
        self.assertIn("bot cannot moderate itself", err.lower())

    def test_can_moderate_self_disallowed(self):
        mod = MagicMock(spec=discord.Member)
        mod.id = 1111
        mod.guild = self.guild
        mod.top_role = self.MockRole("Moderator", 30)

        bot_member = MagicMock(spec=discord.Member)
        bot_member.id = 9999
        bot_member.top_role = self.MockRole("The Raivora", 40)

        can_mod, err = can_moderate(mod, mod, bot_member)
        self.assertFalse(can_mod)
        self.assertIn("cannot moderate yourself", err.lower())

    def test_can_moderate_target_higher_than_bot(self):
        mod = MagicMock(spec=discord.Member)
        mod.id = self.guild.owner_id
        mod.guild = self.guild
        mod.top_role = self.MockRole("Founder", 41)

        target = MagicMock(spec=discord.Member)
        target.id = 2222
        target.guild = self.guild
        target.top_role = self.MockRole("SuperAdmin", 50)
        target.mention = "<@2222>"

        bot_member = MagicMock(spec=discord.Member)
        bot_member.id = 9999
        bot_member.top_role = self.MockRole("The Raivora", 40)

        can_mod, err = can_moderate(mod, target, bot_member)
        self.assertFalse(can_mod)
        self.assertIn("bot's highest role", err.lower())

    def test_can_moderate_success(self):
        mod = MagicMock(spec=discord.Member)
        mod.id = 1111
        mod.guild = self.guild
        mod.top_role = self.MockRole("Moderator", 30)

        target = MagicMock(spec=discord.Member)
        target.id = 3333
        target.guild = self.guild
        target.top_role = self.MockRole("Member", 10)

        bot_member = MagicMock(spec=discord.Member)
        bot_member.id = 9999
        bot_member.top_role = self.MockRole("The Raivora", 40)

        can_mod, err = can_moderate(mod, target, bot_member)
        self.assertTrue(can_mod)
        self.assertEqual(err, "")

    async def test_warn_system(self):
        interaction = MagicMock(spec=discord.Interaction)
        interaction.guild = self.guild
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 1111
        interaction.user.guild = self.guild
        interaction.user.top_role = self.MockRole("Moderator", 30)
        interaction.response.send_message = AsyncMock()

        target = MagicMock(spec=discord.Member)
        target.id = 2222
        target.name = "BadUser"
        target.mention = "<@2222>"
        target.guild = self.guild
        target.top_role = self.MockRole("Member", 10)
        target.display_avatar.url = "https://cdn.discordapp.com/avatars/2222/abc.png"
        target.send = AsyncMock()

        self.guild.me = MagicMock(spec=discord.Member)
        self.guild.me.id = 9999
        self.guild.me.top_role = self.MockRole("The Raivora", 40)

        self.bot.db.add_warning = AsyncMock(return_value=1)
        mock_warning = MagicMock()
        mock_warning.id = 1
        mock_warning.reason = "Spamming general"
        mock_warning.moderator_id = 1111
        mock_warning.created_at = "2026-09-30T12:00:00"
        self.bot.db.get_warnings = AsyncMock(return_value=[mock_warning])
        self.bot.db.get_logging_config = AsyncMock(return_value=MagicMock(moderation_channel_id=None, general_channel_id=None))

        await self.cog.warn.callback(self.cog, interaction, target, "Spamming general")

        self.bot.db.add_warning.assert_awaited_once_with(self.guild.id, target.id, 1111, "Spamming general")
        interaction.response.send_message.assert_awaited_once()

    async def test_clear_purge_boundary(self):
        interaction = MagicMock(spec=discord.Interaction)
        interaction.channel = MagicMock()
        interaction.channel.purge = AsyncMock(return_value=[MagicMock(), MagicMock()])
        interaction.response.send_message = AsyncMock()
        interaction.response.defer = AsyncMock()
        interaction.followup.send = AsyncMock()

        # Invalid amount (< 1)
        await self.cog.clear.callback(self.cog, interaction, 0)
        interaction.response.send_message.assert_awaited_once()

        # Invalid amount (> 100)
        interaction.response.send_message.reset_mock()
        await self.cog.clear.callback(self.cog, interaction, 101)
        interaction.response.send_message.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
