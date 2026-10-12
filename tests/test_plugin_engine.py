"""
Unit test suite for Sentinel Security Plugin Engine.
Verifies loading, reloading, dispatch hooks, and error isolation.
"""

import unittest
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path
import discord

from core.plugin_engine import BaseSecurityPlugin, SecurityPluginEngine
from security_plugins.anti_malware_links import AntiMalwarePlugin
from security_plugins.token_leak_sanitizer import TokenLeakSanitizerPlugin
from security_plugins.alt_account_radar import AltAccountRadarPlugin


class TestSecurityPluginEngine(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = MagicMock()
        self.bot.user.id = 123456789
        self.engine = SecurityPluginEngine(self.bot, plugins_dir=Path("security_plugins"))

    async def test_load_all_plugins(self):
        """Verifies all native security plugins are successfully discovered and loaded."""
        count = await self.engine.load_all()
        self.assertGreaterEqual(count, 3)
        self.assertIn("anti_malware_links", self.engine.plugins)
        self.assertIn("token_leak_sanitizer", self.engine.plugins)
        self.assertIn("alt_account_radar", self.engine.plugins)

    async def test_anti_malware_blocks_dangerous_file(self):
        """Verifies executable file attachment is intercepted and message deleted."""
        plugin = AntiMalwarePlugin(self.bot)
        message = MagicMock(spec=discord.Message)
        message.guild = MagicMock()
        message.author.bot = False
        message.content = "Check this file out"
        attachment = MagicMock()
        attachment.filename = "free_nitro_generator.exe"
        message.attachments = [attachment]
        message.delete = AsyncMock()

        result = await plugin.on_message(message)
        self.assertFalse(result)
        message.delete.assert_awaited_once()

    async def test_token_leak_blocks_and_deletes_bot_token(self):
        """Verifies leaked Discord token in message is purged."""
        plugin = TokenLeakSanitizerPlugin(self.bot)
        message = MagicMock(spec=discord.Message)
        message.guild = MagicMock()
        message.author.bot = False
        message.author.mention = "<@111222>"
        message.channel = MagicMock()
        message.channel.send = AsyncMock()
        message.delete = AsyncMock()
        fake_token = "M" * 24 + "." + "G" * 6 + "." + "a" * 27
        message.content = f"My bot token is {fake_token}"

        result = await plugin.on_message(message)
        self.assertFalse(result)
        message.delete.assert_awaited_once()

    async def test_clean_message_allowed(self):
        """Verifies standard clean message passes through plugin chain."""
        await self.engine.load_all()
        message = MagicMock(spec=discord.Message)
        message.guild = MagicMock()
        message.author.bot = False
        message.content = "Hello everyone, hope you are having a wonderful day!"
        message.attachments = []
        message.delete = AsyncMock()

        allowed = await self.engine.dispatch_message(message)
        self.assertTrue(allowed)
        message.delete.assert_not_called()

    async def test_hot_reload_plugin(self):
        """Verifies hot-reloading a plugin succeeds without breaking state."""
        await self.engine.load_all()
        success = await self.engine.reload_plugin("anti_malware_links")
        self.assertTrue(success)
        self.assertIn("anti_malware_links", self.engine.plugins)


if __name__ == "__main__":
    unittest.main()
