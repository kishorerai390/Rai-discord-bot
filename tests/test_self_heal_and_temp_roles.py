"""
Unit tests for Self-Healing Sentry and Expiring Temporary Roles.
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import discord

from cogs.self_heal import SelfHealCog
from cogs.temp_roles import TempRolesCog, parse_duration_to_seconds


class TestSelfHealAndTempRoles(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot = MagicMock()
        self.bot.wait_until_ready = AsyncMock()
        self.bot.db = MagicMock()
        self.bot.db._db = MagicMock()
        self.bot.user = MagicMock(id=1554732669072445532)

    def test_parse_duration_to_seconds(self):
        """Verifies duration parser handles m, h, d accurately."""
        self.assertEqual(parse_duration_to_seconds("30m"), 1800)
        self.assertEqual(parse_duration_to_seconds("2h"), 7200)
        self.assertEqual(parse_duration_to_seconds("1d"), 86400)
        self.assertEqual(parse_duration_to_seconds("7d"), 604800)
        self.assertIsNone(parse_duration_to_seconds("invalid"))
        self.assertIsNone(parse_duration_to_seconds("10x"))

    async def test_self_heal_audit_flags_open_honeypot(self):
        """Verifies self-healing audit detects honeypot when permissions are unlocked."""
        cog = SelfHealCog(self.bot)
        guild = MagicMock(spec=discord.Guild)
        guild.name = "✦ ʀᴀɪ ʀᴀᴍ ✦"
        guild.id = 1457382179981099090
        guild.default_role = MagicMock(id=1457382179981099090)

        # Mock honeypot channel where view_channel is True (unsafe!)
        mock_hp = MagicMock(spec=discord.TextChannel)
        mock_ow = MagicMock(view_channel=True)
        mock_hp.overwrites_for.return_value = mock_ow

        guild.get_channel.side_effect = lambda cid: mock_hp if cid == 1558168338386129004 else None
        guild.roles = []
        guild.me = MagicMock()
        guild.me.guild_permissions = MagicMock(
            manage_roles=True,
            manage_channels=True,
            ban_members=True,
            view_audit_log=True,
        )

        issues, passes = await cog.audit_guild(guild)
        self.assertTrue(any("Honeypot channel does NOT deny" in i for i in issues))

    async def test_self_heal_audit_passes_when_honeypot_locked(self):
        """Verifies self-healing audit passes when honeypot is strictly denied to @everyone."""
        cog = SelfHealCog(self.bot)
        guild = MagicMock(spec=discord.Guild)
        guild.name = "✦ ʀᴀɪ ʀᴀᴍ ✦"
        guild.id = 1457382179981099090
        guild.default_role = MagicMock(id=1457382179981099090)

        # Mock honeypot channel where view_channel is False (safe!)
        mock_hp = MagicMock(spec=discord.TextChannel)
        mock_ow = MagicMock(view_channel=False)
        mock_hp.overwrites_for.return_value = mock_ow

        guild.get_channel.side_effect = lambda cid: mock_hp
        guild.roles = [MagicMock(name="💖 ╏ 𝓡ᴀɪ 𝕱ᴀᴍ"), MagicMock(name="💎 ╏ 𝓥ɪᴘ 𝕸ᴇᴍʙᴇʀ")]
        guild.me = MagicMock()
        guild.me.guild_permissions = MagicMock(
            manage_roles=True,
            manage_channels=True,
            ban_members=True,
            view_audit_log=True,
        )

        issues, passes = await cog.audit_guild(guild)
        self.assertTrue(any("Honeypot channel strictly locked" in p for p in passes))


if __name__ == "__main__":
    unittest.main()
