import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import discord

from cogs.security import SecurityCog


class TestEveryoneMentionProtection(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = MagicMock()
        self.bot.user.id = 9999999999
        self.bot.db = MagicMock()
        self.bot.db.get_logging_config = AsyncMock(return_value=MagicMock(
            security_channel_id=1546593526073135107,
            moderation_channel_id=None,
            general_channel_id=None,
        ))
        self.bot.db.record_security_incident = AsyncMock()
        self.bot.db.record_violation = AsyncMock()
        self.cog = SecurityCog(self.bot)

    async def test_founder_is_exempt(self):
        guild = MagicMock(spec=discord.Guild)
        guild.id = 1457382179981099090
        guild.owner_id = 123456789

        # Founder author (owner_id)
        founder = MagicMock(spec=discord.Member)
        founder.id = 123456789
        founder.guild = guild
        founder.bot = False
        founder.name = "FounderUser"
        founder.roles = []

        message = MagicMock(spec=discord.Message)
        message.guild = guild
        message.author = founder
        message.webhook_id = None
        message.mention_everyone = True
        message.content = "@everyone Important server update!"
        message.delete = AsyncMock()

        await self.cog._handle_everyone_mention(message)

        # Message should NOT be deleted, member should NOT be kicked
        message.delete.assert_not_called()
        founder.kick.assert_not_called()

    async def test_non_founder_is_kicked_and_deleted(self):
        guild = MagicMock(spec=discord.Guild)
        guild.id = 1457382179981099090
        guild.owner_id = 123456789
        guild.name = "Test Guild"

        class MockRole:
            def __init__(self, name, position):
                self.name = name
                self.position = position
            def __ge__(self, other):
                return self.position >= other.position

        # Regular user
        user = MagicMock(spec=discord.Member)
        user.id = 987654321
        user.bot = False
        user.name = "Spammer"
        user.roles = []
        user.top_role = MockRole("Member", 10)
        user.kick = AsyncMock()
        user.send = AsyncMock()

        # Bot member
        bot_member = MagicMock(spec=discord.Member)
        bot_member.id = self.bot.user.id
        bot_member.top_role = MockRole("Head Admin", 40)
        guild.me = bot_member

        # Private security channel
        sec_channel = MagicMock(spec=discord.TextChannel)
        sec_channel.send = AsyncMock()
        guild.get_channel.return_value = sec_channel

        message = MagicMock(spec=discord.Message)
        message.guild = guild
        message.channel = MagicMock()
        message.channel.name = "general-chat"
        message.channel.mention = "<#1111>"
        message.author = user
        message.webhook_id = None
        message.mention_everyone = True
        message.content = "Hey @everyone check this out"
        message.delete = AsyncMock()

        await self.cog._handle_everyone_mention(message)

        # Offending message must be deleted
        message.delete.assert_awaited_once()

        # Member must be kicked
        user.kick.assert_awaited_once()

        # Incident must be saved in database
        self.bot.db.record_security_incident.assert_awaited_once()

        # Private channel must be notified
        sec_channel.send.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
