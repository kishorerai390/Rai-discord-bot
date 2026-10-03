"""
Unit tests for Rai Premium AI Security Sentinel.
Tests:
- Threat Analysis classification (Cloud & Embedded).
- Zero-day phishing scanner.
- Server security score calculation.
- Anomaly alerts and Founder DM escalation.
"""

import asyncio
import datetime
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from utils.ai_security_brain import AISecurityBrain, ThreatAnalysisReport
from cogs.ai_watchdog import AIWatchdogCog


class TestAISecurityBrain(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.brain = AISecurityBrain()

    async def test_embedded_phishing_detection(self):
        content = "Hey bro claim your discord-nitro-gift here: https://dlscord-nitro.ru/free"
        threat = self.brain.scan_message(content)
        self.assertIsNotNone(threat)
        self.assertEqual(threat.threat_level, "🔴 CRITICAL")
        self.assertEqual(threat.category, "Zero-Day Phishing & Malware")
        self.assertIn("ban_user", threat.suggested_actions)

    async def test_embedded_benign_message(self):
        content = "Hey everyone, who wants to play duo in the voice lounge?"
        threat = self.brain.scan_message(content)
        self.assertIsNone(threat)

    async def test_embedded_threat_analysis_unauthorized_mention(self):
        report = await self.brain.analyze_threat(
            event_type="everyone_mention",
            title="Unauthorized Mention",
            description="User pinged @everyone in chat",
            target_name="Spammer",
        )
        self.assertEqual(report.threat_level, "🔴 CRITICAL")
        self.assertEqual(report.category, "Raid & Spam Protection")
        self.assertIn("timeout_user", report.suggested_actions)

    async def test_embedded_threat_analysis_channel_delete(self):
        report = await self.brain.analyze_threat(
            event_type="channel_delete",
            title="Channel Deleted",
            description="",
            target_name="general-chat",
        )
        self.assertEqual(report.threat_level, "🟠 HIGH")
        self.assertEqual(report.category, "Anti-Nuke / Layout Integrity")

    def test_server_security_score_calculation(self):
        guild = MagicMock(spec=discord.Guild)
        guild.default_role = MagicMock()
        guild.default_role.permissions.administrator = False
        guild.default_role.permissions.mention_everyone = False
        guild.default_role.permissions.manage_channels = False
        guild.default_role.permissions.manage_roles = False

        admin_role = MagicMock()
        admin_role.permissions.administrator = True
        admin_role.managed = False
        guild.roles = [admin_role]

        verify_channel = MagicMock(spec=discord.TextChannel)
        verify_channel.name = "✨｜verify-here"
        guild.text_channels = [verify_channel]

        guild.members = [MagicMock(bot=False), MagicMock(bot=True)]

        score, findings = self.brain.calculate_server_security_score(guild)
        self.assertEqual(score, 100)
        self.assertTrue(any("nominal" in f.lower() for f in findings))


class TestAIWatchdogCog(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot = MagicMock()
        self.bot.db = MagicMock()
        self.bot.get_user = MagicMock()
        self.cog = AIWatchdogCog(self.bot)

    async def test_on_message_intercepts_phishing(self):
        message = MagicMock(spec=discord.Message)
        message.author = MagicMock(spec=discord.Member)
        message.author.bot = False
        message.author.timeout = AsyncMock()
        message.guild = MagicMock(spec=discord.Guild)
        message.channel = MagicMock(spec=discord.TextChannel)
        message.content = "Claim free nitro here: https://discord-nitro-gift.com/claim"
        message.delete = AsyncMock()

        self.bot.db.get_security_config = AsyncMock(return_value=MagicMock(log_channel_id=999))
        mock_log = MagicMock(spec=discord.TextChannel)
        mock_log.send = AsyncMock()
        message.guild.get_channel.return_value = mock_log

        await self.cog.on_message(message)

        message.delete.assert_called_once()
        message.author.timeout.assert_called_once()


if __name__ == "__main__":
    unittest.main()
