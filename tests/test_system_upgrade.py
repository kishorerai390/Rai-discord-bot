"""
Unit tests for Deep Diagnostics and System Optimization Cog.
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import discord

from cogs.system_upgrade import SystemUpgradeCog


class TestSystemUpgrade(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot = MagicMock()
        self.bot.wait_until_ready = AsyncMock()
        self.bot.db = MagicMock()
        self.bot.db._db = MagicMock()
        self.bot.user = MagicMock(id=1554732669072445532)
        self.bot.latency = 0.015  # 15ms

    async def test_bot_upgrade_manifest(self):
        """Verifies /bot_upgrade command returns complete capability manifest."""
        cog = SystemUpgradeCog(self.bot)
        interaction = MagicMock(spec=discord.Interaction)
        interaction.user = MagicMock(guild_permissions=MagicMock(administrator=True))
        interaction.response = AsyncMock()

        with patch("cogs.system_upgrade.is_admin_or_owner", return_value=True):
            await cog.upgrade_manifest.callback(cog, interaction)
            interaction.response.send_message.assert_called_once()
            args, kwargs = interaction.response.send_message.call_args
            embed = kwargs["embed"]
            self.assertIn("BOT UPGRADE & CAPABILITY MANIFEST", embed.title)
            self.assertIn("Casino & Arcades", embed.description)
            self.assertIn("Community Prediction", embed.description)
            self.assertIn("Golden State Self-Healing", embed.description)
            self.assertIn("Isolated Report Routing", embed.description)


if __name__ == "__main__":
    unittest.main()
