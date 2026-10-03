import unittest
from unittest.mock import AsyncMock, MagicMock
import discord

from cogs.welcome import WelcomeCog, format_template
from database.models import GuildConfig, WelcomeConfig


class TestWelcome(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot = MagicMock()
        self.bot.db = MagicMock()
        self.cog = WelcomeCog(self.bot)

        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = 1457382179981099090
        self.guild.name = "RAI FAM"
        self.guild.member_count = 50
        self.guild.icon = None

        self.member = MagicMock(spec=discord.Member)
        self.member.id = 12345
        self.member.name = "NewPlayer"
        self.member.mention = "<@12345>"
        self.member.guild = self.guild
        self.member.bot = False
        self.member.display_avatar.url = "https://cdn.discordapp.com/avatars/12345/avatar.png"
        self.member.created_at = discord.utils.utcnow()
        self.member.add_roles = AsyncMock()
        self.member.send = AsyncMock()

    def test_format_template(self):
        template = "Hello {user} ({username})! Welcome to {server}. We now have {member_count} members!"
        res = format_template(template, self.member)
        self.assertEqual(res, "Hello <@12345> (NewPlayer)! Welcome to RAI FAM. We now have 50 members!")

    async def test_welcome_disabled_skips(self):
        self.bot.db.get_or_create_guild_config = AsyncMock(return_value=GuildConfig(
            guild_id=self.guild.id,
            welcome_enabled=False,
        ))

        await self.cog.on_member_join(self.member)
        self.member.add_roles.assert_not_called()
        self.member.send.assert_not_called()

    async def test_welcome_with_autorole_and_channel_embed(self):
        self.bot.db.get_or_create_guild_config = AsyncMock(return_value=GuildConfig(
            guild_id=self.guild.id,
            welcome_enabled=True,
        ))

        class MockRole:
            def __init__(self, position):
                self.position = position
            def __lt__(self, other):
                return self.position < other.position

        mock_role = MockRole(10)
        self.guild.get_role.return_value = mock_role

        bot_member = MagicMock(spec=discord.Member)
        bot_member.top_role = MockRole(40)
        bot_member.guild_permissions = discord.Permissions(manage_roles=True)
        self.guild.me = bot_member

        channel = MagicMock(spec=discord.TextChannel)
        channel.send = AsyncMock()
        self.guild.get_channel.return_value = channel

        self.bot.db.get_welcome_config = AsyncMock(return_value=WelcomeConfig(
            guild_id=self.guild.id,
            welcome_channel_id=9876,
            welcome_message="Welcome to {server}, {user}!",
            autorole_id=5555,
            embed_enabled=True,
            dm_enabled=True,
        ))

        await self.cog.on_member_join(self.member)

        # Autorole added
        self.member.add_roles.assert_awaited_once_with(mock_role, reason="Welcome Autorole")

        # Channel message sent
        channel.send.assert_awaited_once()

        # DM sent
        self.member.send.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
