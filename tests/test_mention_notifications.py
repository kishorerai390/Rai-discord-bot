"""
Unit tests for MentionNotificationsCog.
Validates tag notifications DM functionality, embed formatting, link buttons,
anti-spam cooldowns, and user/guild opt-out controls.
"""

import asyncio
import datetime
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import discord
from cogs.mention_notifications import MentionNotificationsCog, NOTIFICATION_COLOR, COOLDOWN_SECONDS


class TestMentionNotifications(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = MagicMock()
        self.bot.db = MagicMock()
        self.bot.db.get_guild_mention_notification = AsyncMock(return_value=True)
        self.bot.db.get_user_mention_notification = AsyncMock(return_value=True)
        self.bot.db.set_user_mention_notification = AsyncMock()
        self.bot.db.set_guild_mention_notification = AsyncMock()
        
        self.cog = MentionNotificationsCog(self.bot)

        # Mock Guild
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = 1457382179981099090
        self.guild.name = "RAI FAM"
        self.guild.icon = None

        # Mock Channel
        self.channel = MagicMock(spec=discord.TextChannel)
        self.channel.name = "general-chat"
        self.channel.category = MagicMock()
        self.channel.category.name = "COMMUNITY"

        # Mock Sender Member
        self.sender = MagicMock(spec=discord.Member)
        self.sender.id = 11111111
        self.sender.name = "TheRealThor"
        self.sender.mention = "<@11111111>"
        self.sender.bot = False

        # Mock Recipient Member
        self.recipient = MagicMock(spec=discord.Member)
        self.recipient.id = 22222222
        self.recipient.name = "Rai"
        self.recipient.mention = "<@22222222>"
        self.recipient.bot = False
        self.recipient.send = AsyncMock()

    async def test_successful_mention_dm(self):
        """Verifies DM notification is dispatched with correct format when member is tagged."""
        message = MagicMock(spec=discord.Message)
        message.guild = self.guild
        message.channel = self.channel
        message.author = self.sender
        message.content = "Hey @Rai check this out!"
        message.mentions = [self.recipient]
        message.attachments = []
        message.embeds = []
        message.stickers = []
        message.jump_url = "https://discord.com/channels/1457382179981099090/1545502850057244762/123456789"
        message.created_at = datetime.datetime.now(datetime.timezone.utc)

        await self.cog.on_message(message)

        self.recipient.send.assert_called_once()
        _, kwargs = self.recipient.send.call_args
        embed = kwargs.get("embed")
        view = kwargs.get("view")

        self.assertIsNotNone(embed)
        self.assertEqual(embed.title, f"🔔 You were tagged in {self.guild.name}!")
        self.assertEqual(embed.color.value, NOTIFICATION_COLOR)
        self.assertIn("**Sender:** TheRealThor ( <@11111111> )", embed.description)
        self.assertIn(f"**Server:** {self.guild.name}", embed.description)
        self.assertIn("COMMUNITY > 💬 #general-chat", embed.description)
        self.assertIn("> Hey @Rai check this out!", embed.description)
        self.assertIn("[Click Here to View Message]", embed.description)

        self.assertIsNotNone(view)
        # Check link button url
        self.assertEqual(len(view.children), 1)
        self.assertEqual(view.children[0].url, message.jump_url)

    async def test_ignores_self_mention(self):
        """Does not send DM if author mentions themselves."""
        message = MagicMock(spec=discord.Message)
        message.guild = self.guild
        message.channel = self.channel
        message.author = self.sender
        message.content = "I mention myself @TheRealThor"
        message.mentions = [self.sender]
        message.created_at = datetime.datetime.now(datetime.timezone.utc)

        await self.cog.on_message(message)
        self.recipient.send.assert_not_called()

    async def test_ignores_bot_recipient(self):
        """Does not send DM if mentioned entity is a bot."""
        bot_user = MagicMock(spec=discord.Member)
        bot_user.id = 99999999
        bot_user.bot = True
        bot_user.send = AsyncMock()

        message = MagicMock(spec=discord.Message)
        message.guild = self.guild
        message.channel = self.channel
        message.author = self.sender
        message.content = "Hey @Bot"
        message.mentions = [bot_user]
        message.created_at = datetime.datetime.now(datetime.timezone.utc)

        await self.cog.on_message(message)
        bot_user.send.assert_not_called()

    async def test_anti_spam_cooldown(self):
        """Ensures rapid successive tags do not flood recipient DMs."""
        message = MagicMock(spec=discord.Message)
        message.guild = self.guild
        message.channel = self.channel
        message.author = self.sender
        message.content = "Spam 1 @Rai"
        message.mentions = [self.recipient]
        message.attachments = []
        message.embeds = []
        message.stickers = []
        message.jump_url = "https://discord.com/msg1"
        message.created_at = datetime.datetime.now(datetime.timezone.utc)

        # First message passes
        await self.cog.on_message(message)
        self.assertEqual(self.recipient.send.call_count, 1)

        # Immediate second message should be rate-limited
        message.content = "Spam 2 @Rai"
        await self.cog.on_message(message)
        self.assertEqual(self.recipient.send.call_count, 1)

    async def test_user_opt_out_respected(self):
        """Does not send DM if recipient opted out of mention notifications."""
        self.bot.db.get_user_mention_notification = AsyncMock(return_value=False)

        message = MagicMock(spec=discord.Message)
        message.guild = self.guild
        message.channel = self.channel
        message.author = self.sender
        message.content = "Hey @Rai"
        message.mentions = [self.recipient]
        message.created_at = datetime.datetime.now(datetime.timezone.utc)

        await self.cog.on_message(message)
        self.recipient.send.assert_not_called()

    async def test_handles_closed_dms_gracefully(self):
        """Silently handles discord.Forbidden when recipient has DMs disabled."""
        self.recipient.send.side_effect = discord.Forbidden(MagicMock(), "Cannot send messages to this user")

        message = MagicMock(spec=discord.Message)
        message.guild = self.guild
        message.channel = self.channel
        message.author = self.sender
        message.content = "Hey @Rai"
        message.mentions = [self.recipient]
        message.attachments = []
        message.embeds = []
        message.stickers = []
        message.jump_url = "https://discord.com/msg"
        message.created_at = datetime.datetime.now(datetime.timezone.utc)

        # Should not raise exception
        await self.cog.on_message(message)


if __name__ == "__main__":
    unittest.main()
