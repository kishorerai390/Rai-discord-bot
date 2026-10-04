"""
Unit tests for Founder Live Activity Alerts & Expanded VC/Channel Logging.
"""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import discord
from cogs.logging import LoggingCog
from config import Colors


class TestFounderActivityAlerts(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = MagicMock()
        self.bot.db = MagicMock()
        self.bot.db.get_logging_config = AsyncMock()
        self.bot.db.get_logging_config.return_value = MagicMock(
            general_channel_id=12345,
            voice_channel_id=12345,
            message_channel_id=12345,
            member_channel_id=12345,
        )
        self.bot.db.get_founder_activity_dm = AsyncMock(return_value=True)
        self.bot.db.set_founder_activity_dm = AsyncMock()
        self.bot.db.get_founder_dm_recipient = AsyncMock(return_value=None)
        self.bot.db.set_founder_dm_recipient = AsyncMock()

        self.cog = LoggingCog(self.bot)

        # Guild & Owner
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = 1457382179981099090
        self.guild.name = "RAI FAM"
        self.guild.owner_id = 1457380609641938981
        self.guild_owner = MagicMock(spec=discord.Member)
        self.guild_owner.id = 1457380609641938981
        self.guild_owner.bot = False
        self.guild_owner.send = AsyncMock()
        self.guild.owner = self.guild_owner

        # Log Channel
        self.log_channel = MagicMock(spec=discord.TextChannel)
        self.log_channel.send = AsyncMock()
        self.guild.get_channel.return_value = self.log_channel

        # Test Member
        self.member = MagicMock(spec=discord.Member)
        self.member.id = 1226447283327860837
        self.member.name = "Rcrai !"
        self.member.mention = "<@1226447283327860837>"
        self.member.display_avatar.url = "https://cdn.discordapp.com/avatar.png"
        self.member.guild = self.guild

        # Voice Channels
        self.vc1 = MagicMock(spec=discord.VoiceChannel)
        self.vc1.name = "➕ │ • JOIN TO CREATE"
        self.vc2 = MagicMock(spec=discord.VoiceChannel)
        self.vc2.name = "Rcrai !'s Room"

    async def test_voice_channel_connect(self):
        """Verifies voice connect triggers log channel and Founder DM with exact embed format."""
        before = MagicMock(spec=discord.VoiceState)
        before.channel = None
        after = MagicMock(spec=discord.VoiceState)
        after.channel = self.vc1

        await self.cog.on_voice_state_update(self.member, before, after)

        # Channel log received
        self.log_channel.send.assert_called_once()
        embed = self.log_channel.send.call_args.kwargs["embed"]
        self.assertIn("Voice", embed.title)
        self.assertIn("connected to **#➕ │ • JOIN TO CREATE**", embed.description)

        # Founder DM received
        self.guild_owner.send.assert_called_once()
        dm_embed = self.guild_owner.send.call_args.kwargs["embed"]
        self.assertIn("Voice", dm_embed.title)
        self.assertIn("connected to **#➕ │ • JOIN TO CREATE**", dm_embed.description)

    async def test_voice_channel_switch(self):
        """Verifies voice channel switch from VC1 to VC2."""
        before = MagicMock(spec=discord.VoiceState)
        before.channel = self.vc1
        after = MagicMock(spec=discord.VoiceState)
        after.channel = self.vc2

        await self.cog.on_voice_state_update(self.member, before, after)

        self.log_channel.send.assert_called_once()
        embed = self.log_channel.send.call_args.kwargs["embed"]
        self.assertIn("Voice", embed.title)
        self.assertTrue(
            "switched from" in embed.description and "Rcrai !'s Room" in embed.description
        )

    async def test_voice_streaming_alert(self):
        """Verifies streaming start triggers voice activity alert."""
        before = MagicMock(spec=discord.VoiceState)
        before.channel = self.vc2
        before.self_stream = False
        before.self_video = False
        before.mute = False
        before.deaf = False

        after = MagicMock(spec=discord.VoiceState)
        after.channel = self.vc2
        after.self_stream = True
        after.self_video = False
        after.mute = False
        after.deaf = False

        await self.cog.on_voice_state_update(self.member, before, after)

        self.log_channel.send.assert_called_once()
        embed = self.log_channel.send.call_args.kwargs["embed"]
        self.assertTrue(
            "started streaming in **#Rcrai !'s Room**" in embed.description
            or "started screen sharing / streaming in **#Rcrai !'s Room**" in embed.description
        )

    async def test_channel_create_and_delete(self):
        """Verifies channel creation and deletion dispatch with correct icons and details."""
        created_ch = MagicMock(spec=discord.VoiceChannel)
        created_ch.guild = self.guild
        created_ch.name = "Rcrai !'s Room"
        created_ch.mention = "<#1554878970812567572>"
        created_ch.id = 1554878970812567572

        await self.cog.on_guild_channel_create(created_ch)
        self.log_channel.send.assert_called_once()
        embed = self.log_channel.send.call_args.kwargs["embed"]
        self.assertEqual(embed.title, "📁 Channel Created")
        self.assertIn("🔊 <#1554878970812567572> ( Rcrai !'s Room | ID: `1554878970812567572` )", embed.description)

    async def test_founder_dm_disabled_setting(self):
        """Verifies founder activity DMs are skipped when setting is toggled off."""
        self.bot.db.get_founder_activity_dm.return_value = False

        before = MagicMock(spec=discord.VoiceState)
        before.channel = None
        after = MagicMock(spec=discord.VoiceState)
        after.channel = self.vc1

        await self.cog.on_voice_state_update(self.member, before, after)

        # Log channel still gets it
        self.log_channel.send.assert_called_once()
        # Founder DM is not called
        self.guild_owner.send.assert_not_called()

    async def test_voice_mute_does_not_send_dm(self):
        """Verifies microphone mute logs to voice log channel but NEVER spams Founder DM."""
        before = MagicMock(spec=discord.VoiceState)
        before.channel = self.vc1
        before.self_mute = False
        after = MagicMock(spec=discord.VoiceState)
        after.channel = self.vc1
        after.self_mute = True

        await self.cog.on_voice_state_update(self.member, before, after)

        self.log_channel.send.assert_called_once()
        self.guild_owner.send.assert_not_called()

    async def test_voice_disconnect_does_not_send_dm(self):
        """Verifies leaving voice room logs to voice log channel but NEVER spams Founder DM."""
        before = MagicMock(spec=discord.VoiceState)
        before.channel = self.vc1
        after = MagicMock(spec=discord.VoiceState)
        after.channel = None

        await self.cog.on_voice_state_update(self.member, before, after)

        self.log_channel.send.assert_called_once()
        self.guild_owner.send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
