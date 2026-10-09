"""
Unit tests for Stealth Honeypot, Anti-Ghost Ping, and Booster Concierge features.
"""

import datetime
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import discord

from cogs.security import SecurityCog
from cogs.roles import RolesCog


class TestHoneypotAndGhostPing(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = MagicMock()
        self.bot.db = MagicMock()
        self.bot.db.record_security_incident = AsyncMock()
        self.bot.db.record_violation = AsyncMock()
        self.bot.db.get_logging_config = AsyncMock(return_value=MagicMock(security_channel_id=1555283378612478072, moderation_channel_id=None, general_channel_id=None))
        self.cog = SecurityCog(self.bot)

    async def test_honeypot_triggers_ban_and_incident(self):
        guild = MagicMock(spec=discord.Guild)
        guild.id = 99999
        guild.owner_id = 11111
        
        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 1558168338386129004  # Honeypot channel ID
        channel.name = "honeypot-trap"
        channel.mention = "<#1558168338386129004>"
        
        author = MagicMock(spec=discord.Member)
        author.id = 22222
        author.name = "raider_bot"
        author.mention = "<@22222>"
        author.bot = False
        author.ban = AsyncMock()

        msg = MagicMock(spec=discord.Message)
        msg.guild = guild
        msg.channel = channel
        msg.author = author
        msg.content = "FREE NITRO LINK CLICK HERE"
        msg.delete = AsyncMock()

        with patch.object(self.cog, "_send_private_security_alert", new_callable=AsyncMock) as mock_alert:
            handled = await self.cog._handle_honeypot_trap(msg)
            self.assertTrue(handled)
            msg.delete.assert_awaited_once()
            author.ban.assert_awaited_once()
            self.bot.db.record_security_incident.assert_awaited_once()
            mock_alert.assert_awaited_once()

    async def test_ghost_ping_detection(self):
        guild = MagicMock(spec=discord.Guild)
        guild.id = 99999
        
        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 88888
        channel.name = "general"
        channel.mention = "<#88888>"
        channel.send = AsyncMock()
        
        author = MagicMock(spec=discord.Member)
        author.id = 33333
        author.name = "troll_user"
        author.mention = "<@33333>"
        author.bot = False

        target_member = MagicMock(spec=discord.Member)
        target_member.id = 44444
        target_member.mention = "<@44444>"
        target_member.bot = False

        msg = MagicMock(spec=discord.Message)
        msg.guild = guild
        msg.channel = channel
        msg.author = author
        msg.mentions = [target_member]
        msg.role_mentions = []
        msg.content = "Hey @target look here!"
        msg.created_at = discord.utils.utcnow()

        with patch.object(self.cog, "_send_private_security_alert", new_callable=AsyncMock) as mock_alert:
            await self.cog.on_message_delete(msg)
            mock_alert.assert_awaited_once()
            channel.send.assert_awaited_once()


class TestBoosterConcierge(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = MagicMock()
        self.cog = RolesCog(self.bot)

    async def test_booster_concierge_delivery(self):
        guild = MagicMock(spec=discord.Guild)
        guild.id = 99999
        guild.name = "The Raivora Sanctuary"
        guild.icon = None

        lounge_channel = MagicMock(spec=discord.TextChannel)
        lounge_channel.id = 1557479371001045056
        lounge_channel.send = AsyncMock()

        guild.get_channel = MagicMock(return_value=lounge_channel)

        member = MagicMock(spec=discord.Member)
        member.guild = guild
        member.id = 55555
        member.display_name = "NitroSupporter"
        member.mention = "<@55555>"
        member.display_avatar.url = "http://avatar.url"
        member.send = AsyncMock()

        await self.cog._handle_booster_concierge(member)
        lounge_channel.send.assert_awaited_once()
        member.send.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
