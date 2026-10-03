import unittest
from unittest.mock import AsyncMock, MagicMock
import discord

from cogs.automod import AutoModCog, EMOJI_REGEX, INVITE_REGEX, SUSPICIOUS_REGEX
from database.models import AutoModConfig, GuildConfig


class TestAutoMod(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot = MagicMock()
        self.bot.user.id = 999999
        self.bot.db = MagicMock()
        self.cog = AutoModCog(self.bot)

    def test_invite_regex(self):
        valid_invites = [
            "https://discord.gg/raifam",
            "http://discord.gg/xyz123",
            "discord.gg/test",
            "https://discord.com/invite/community",
            "Join here: discord.gg/abcdef now!",
        ]
        for url in valid_invites:
            self.assertIsNotNone(INVITE_REGEX.search(url), f"Failed to match invite: {url}")

        non_invites = [
            "https://google.com",
            "https://discord.com/channels/123/456",
            "Check my github repo",
        ]
        for url in non_invites:
            self.assertIsNone(INVITE_REGEX.search(url), f"False positive on: {url}")

    def test_suspicious_regex(self):
        suspicious_urls = [
            "https://steamcommunity-gift.com/free",
            "http://discord-nitro-free.com/claim",
            "free-nitro-gift.com/get",
            "https://gift-nitro-promo.com/free",
            "dlscord.com/free-nitro",
        ]
        for url in suspicious_urls:
            self.assertIsNotNone(SUSPICIOUS_REGEX.search(url), f"Failed to match scam: {url}")

        safe_urls = [
            "https://discord.com",
            "https://store.steampowered.com",
            "https://youtube.com",
        ]
        for url in safe_urls:
            self.assertIsNone(SUSPICIOUS_REGEX.search(url), f"False positive on safe url: {url}")

    def test_custom_emoji_regex(self):
        text = "Hello <:pepe:123456789012345678> and <a:party:987654321098765432>!"
        matches = EMOJI_REGEX.findall(text)
        self.assertEqual(len(matches), 2)
        self.assertIn("<:pepe:123456789012345678>", matches)
        self.assertIn("<a:party:987654321098765432>", matches)

    async def test_automod_disabled_skips(self):
        message = MagicMock(spec=discord.Message)
        message.guild = MagicMock(spec=discord.Guild)
        message.guild.id = 12345
        message.guild.owner_id = 99999
        message.author = MagicMock(spec=discord.Member)
        message.author.id = 11111
        message.author.bot = False
        message.author.guild_permissions = discord.Permissions(send_messages=True)
        message.author.roles = []
        message.content = "discord.gg/spam"
        message.delete = AsyncMock()

        self.bot.db.is_whitelisted = AsyncMock(return_value=False)
        self.bot.db.get_or_create_guild_config = AsyncMock(return_value=GuildConfig(
            guild_id=12345,
            automod_enabled=False,
        ))

        await self.cog.on_message(message)
        message.delete.assert_not_called()

    async def test_automod_invite_block(self):
        message = MagicMock(spec=discord.Message)
        message.guild = MagicMock(spec=discord.Guild)
        message.guild.id = 12345
        message.guild.owner_id = 99999
        message.author = MagicMock(spec=discord.Member)
        message.author.id = 11111
        message.author.bot = False
        message.author.guild_permissions = discord.Permissions(send_messages=True)
        message.author.roles = []
        message.content = "Come join my server: https://discord.gg/invitelink"
        message.channel = MagicMock()
        message.channel.name = "general"
        message.channel.send = AsyncMock()
        message.delete = AsyncMock()
        message.author.send = AsyncMock()

        self.bot.db.is_whitelisted = AsyncMock(return_value=False)
        self.bot.db.get_or_create_guild_config = AsyncMock(return_value=GuildConfig(
            guild_id=12345,
            automod_enabled=True,
        ))
        self.bot.db.get_automod_config = AsyncMock(return_value=AutoModConfig(
            guild_id=12345,
            invite_links_block=True,
            action="delete",
        ))
        self.bot.db.record_automod_log = AsyncMock()
        self.bot.db.record_violation = AsyncMock()
        self.bot.db.get_logging_config = AsyncMock(return_value=MagicMock(automod_channel_id=None, general_channel_id=None))

        await self.cog.on_message(message)
        message.delete.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
