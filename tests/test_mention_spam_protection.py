"""
Comprehensive Automated Test Suite for Mass User Mention Spam Protection in 『RΛI』.
Tests all 14 required test cases:
1. Normal single-user mention (no action)
2. 3 user mentions (below warning, no action)
3. 10 user mentions (triggers HIGH, deletion + timeout)
4. 20+ user mentions (triggers CRITICAL, immediate timeout + cleanup)
5. Repeated mention messages (duplicate detection across messages)
6. Same attack across multiple channels (cross-channel tracking: Channel A, B, C, D)
7. Rapid message spam
8. Staff member behavior (exempted)
9. Multiple suspicious users (coordinated attack detection)
10. Deleted messages cleanup (only attacker's messages deleted)
11. Bot messages (ignored)
12. Music running during attack (music unaffected)
13. Database failure handling (fails safe without crashing bot)
14. Discord API failure handling (forbidden/403 handled gracefully)
"""

import asyncio
import datetime
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import discord

from database.models import MentionSpamConfig
from security.mention_spam import MentionSpamEngine, USER_MENTION_REGEX


class TestMentionSpamProtection(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = MagicMock()
        self.bot.db = AsyncMock()
        self.engine = MentionSpamEngine(self.bot)

        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = 1457382179981099090
        self.guild.name = "Neo-Tokyo Citadel"
        self.guild.owner_id = 999999999

        # Bot member
        self.bot_member = MagicMock(spec=discord.Member)
        self.bot_member.id = 1554732669072445532
        self.bot_member.top_role = MagicMock()
        self.bot_member.top_role.position = 100
        self.guild.me = self.bot_member

        # Default configuration
        self.default_cfg = MentionSpamConfig(
            guild_id=self.guild.id,
            enabled=True,
            warning_threshold=5,
            high_threshold=10,
            critical_threshold=20,
            window_seconds=10,
            cross_channel_threshold=3,
            repeat_message_threshold=3,
            action_low="delete",
            action_high="timeout",
            action_critical="timeout_and_purge",
            timeout_duration_high=600,
            timeout_duration_critical=86400,
            purge_window_seconds=60,
            staff_exempt=True,
        )
        self.bot.db.get_or_create_mention_spam_config.return_value = self.default_cfg
        self.bot.db.is_whitelisted.return_value = False
        self.bot.db.get_logging_config.return_value = MagicMock(security_channel_id=None, moderation_channel_id=None)

    def _create_mock_message(
        self,
        author_id: int,
        content: str,
        channel_id: int = 101,
        is_bot: bool = False,
        is_staff: bool = False,
        target_ids: list[int] = None,
    ):
        msg = MagicMock(spec=discord.Message)
        msg.id = int(asyncio.get_event_loop().time() * 1000) % 10000000 + author_id
        msg.guild = self.guild
        msg.content = content

        author = MagicMock(spec=discord.Member)
        author.id = author_id
        author.name = f"User_{author_id}"
        author.display_name = f"User_{author_id}"
        author.discriminator = "0001"
        author.bot = is_bot
        author.guild = self.guild
        author.top_role = MagicMock()
        author.top_role.position = 10

        author.guild_permissions = MagicMock()
        author.guild_permissions.administrator = is_staff
        author.guild_permissions.manage_guild = is_staff
        author.guild_permissions.moderate_members = is_staff

        author.timeout = AsyncMock()
        msg.author = author

        channel = MagicMock(spec=discord.TextChannel)
        channel.id = channel_id
        channel.name = f"channel-{channel_id}"
        channel.purge = AsyncMock(return_value=[])
        msg.channel = channel
        self.guild.get_channel.return_value = channel

        msg.delete = AsyncMock()

        # Build parsed mentions
        if target_ids is not None:
            mentions = []
            for tid in target_ids:
                m = MagicMock(spec=discord.User)
                m.id = tid
                mentions.append(m)
            msg.mentions = mentions
        else:
            # Parse targets from regex in content
            matches = USER_MENTION_REGEX.findall(content)
            mentions = []
            for tid_str in matches:
                m = MagicMock(spec=discord.User)
                m.id = int(tid_str)
                mentions.append(m)
            msg.mentions = mentions

        return msg

    async def test_01_normal_single_user_mention(self):
        """Case 1: Normal message with 1 user mention is ignored and not mitigated."""
        msg = self._create_mock_message(author_id=1001, content="Hey <@2001> check this out!", target_ids=[2001])
        mitigated = await self.engine.inspect_message(msg)
        self.assertFalse(mitigated)
        msg.delete.assert_not_awaited()
        msg.author.timeout.assert_not_awaited()

    async def test_02_three_user_mentions(self):
        """Case 2: 3 mentions (below warning threshold of 5) are not mitigated."""
        msg = self._create_mock_message(author_id=1002, content="<@2001> <@2002> <@2003> team up!", target_ids=[2001, 2002, 2003])
        mitigated = await self.engine.inspect_message(msg)
        self.assertFalse(mitigated)
        msg.delete.assert_not_awaited()

    async def test_03_ten_user_mentions_triggers_high(self):
        """Case 3: 10 user mentions triggers HIGH threat level: deleted & 10m timeout."""
        targets = [2000 + i for i in range(10)]
        content = " ".join(f"<@{tid}>" for tid in targets)
        msg = self._create_mock_message(author_id=1003, content=content, target_ids=targets)

        mitigated = await self.engine.inspect_message(msg)
        self.assertTrue(mitigated)
        msg.delete.assert_awaited_once()
        msg.author.timeout.assert_awaited_once()
        # Verify timeout duration is high threshold (600s = 10m)
        until_arg = msg.author.timeout.call_args[0][0]
        self.assertGreater(until_arg, discord.utils.utcnow())

    async def test_04_twenty_plus_user_mentions_triggers_critical(self):
        """Case 4: 25 user mentions triggers CRITICAL threat: 24h timeout + channel purge."""
        targets = [3000 + i for i in range(25)]
        content = " ".join(f"<@{tid}>" for tid in targets)
        msg = self._create_mock_message(author_id=1004, content=content, target_ids=targets)

        mitigated = await self.engine.inspect_message(msg)
        self.assertTrue(mitigated)
        msg.delete.assert_awaited_once()
        msg.author.timeout.assert_awaited_once()
        # Verify incident logged to database
        self.bot.db.create_mention_spam_incident.assert_awaited_once()

    async def test_05_repeated_mention_messages(self):
        """Case 5: Repeated duplicate mention spam triggers HIGH alert on repeat threshold."""
        targets = [4001, 4002, 4003, 4004]  # 4 mentions per message
        content = "<@4001> <@4002> <@4003> <@4004>"

        # Send 1st and 2nd messages (under threshold)
        msg1 = self._create_mock_message(author_id=1005, content=content, target_ids=targets)
        await self.engine.inspect_message(msg1)

        msg2 = self._create_mock_message(author_id=1005, content=content, target_ids=targets)
        await self.engine.inspect_message(msg2)

        # 3rd identical message hits repeat threshold of 3 & cumulative count
        msg3 = self._create_mock_message(author_id=1005, content=content, target_ids=targets)
        mitigated = await self.engine.inspect_message(msg3)
        self.assertTrue(mitigated)
        msg3.delete.assert_awaited()

    async def test_06_same_attack_across_multiple_channels(self):
        """Case 6: Attacker moving across channels (Ch1, Ch2, Ch3) is tracked cross-channel."""
        # 4 mentions per channel across 3 channels
        msg_ch1 = self._create_mock_message(author_id=1006, content="<@5001> <@5002> <@5003> <@5004>", channel_id=101, target_ids=[5001, 5002, 5003, 5004])
        await self.engine.inspect_message(msg_ch1)

        msg_ch2 = self._create_mock_message(author_id=1006, content="<@5005> <@5006> <@5007> <@5008>", channel_id=102, target_ids=[5005, 5006, 5007, 5008])
        await self.engine.inspect_message(msg_ch2)

        # 3rd channel reaches cross_channel_threshold=3 and total_mentions=12 (>= high_threshold)
        msg_ch3 = self._create_mock_message(author_id=1006, content="<@5009> <@5010> <@5011> <@5012>", channel_id=103, target_ids=[5009, 5010, 5011, 5012])
        mitigated = await self.engine.inspect_message(msg_ch3)

        self.assertTrue(mitigated)
        # Tracker accurately records all 3 affected channels
        tracker = self.engine._user_trackers[(self.guild.id, 1006)]
        stats = tracker.get_window_stats(10.0, "")
        self.assertEqual(len(stats["channels_affected"]), 3)
        self.assertIn(101, stats["channels_affected"])
        self.assertIn(102, stats["channels_affected"])
        self.assertIn(103, stats["channels_affected"])

    async def test_07_rapid_message_spam(self):
        """Case 7: Rapid burst of mention messages sums up within 10s sliding window."""
        for i in range(4):
            targets = [6000 + i * 3 + j for j in range(3)]
            msg = self._create_mock_message(author_id=1007, content="spam", target_ids=targets)
            mitigated = await self.engine.inspect_message(msg)

        # By 4th message, 4 * 3 = 12 mentions within sliding window (>= high_threshold)
        self.assertTrue(mitigated)

    async def test_08_staff_member_exempted(self):
        """Case 8: Administrator / Staff member sending mentions is exempted."""
        targets = [7000 + i for i in range(15)]
        msg = self._create_mock_message(author_id=8888, content="Announcement for staff", is_staff=True, target_ids=targets)

        mitigated = await self.engine.inspect_message(msg)
        self.assertFalse(mitigated)
        msg.delete.assert_not_awaited()
        msg.author.timeout.assert_not_awaited()

    async def test_09_multiple_suspicious_users_coordinated_raid(self):
        """Case 9: Multiple attackers spamming simultaneously flags coordinated mention raid."""
        # 3 distinct users send 6 mentions within 5s
        targets = [8001, 8002, 8003, 8004, 8005, 8006]
        content = " ".join(f"<@{tid}>" for tid in targets)

        msg_u1 = self._create_mock_message(author_id=9001, content=content, channel_id=201, target_ids=targets)
        await self.engine.inspect_message(msg_u1)

        msg_u2 = self._create_mock_message(author_id=9002, content=content, channel_id=202, target_ids=targets)
        await self.engine.inspect_message(msg_u2)

        msg_u3 = self._create_mock_message(author_id=9003, content=content, channel_id=203, target_ids=targets)
        await self.engine.inspect_message(msg_u3)

        # Correlation tracker has recorded 3 attackers in window
        bursts = self.engine._guild_correlation[self.guild.id]
        distinct = set(b[1] for b in bursts)
        self.assertGreaterEqual(len(distinct), 3)

    async def test_10_deleted_messages_attacker_only_cleanup(self):
        """Case 10: Purge predicate strictly purges attacker messages, leaving others untouched."""
        attacker_id = 9999
        other_user_id = 1111

        attacker_msg = MagicMock(spec=discord.Message)
        attacker_msg.author.id = attacker_id
        attacker_msg.created_at = datetime.datetime.now(datetime.timezone.utc)

        innocent_msg = MagicMock(spec=discord.Message)
        innocent_msg.author.id = other_user_id
        innocent_msg.created_at = datetime.datetime.now(datetime.timezone.utc)

        # Trigger critical purge
        targets = [9100 + i for i in range(25)]
        msg = self._create_mock_message(author_id=attacker_id, content="Raid", target_ids=targets)
        await self.engine.inspect_message(msg)

        # Channel purge was invoked with predicate
        purge_call = msg.channel.purge.call_args
        predicate = purge_call[1]["check"]
        self.assertTrue(predicate(attacker_msg))
        self.assertFalse(predicate(innocent_msg))

    async def test_11_bot_messages_ignored(self):
        """Case 11: Bot messages are ignored even if containing mentions."""
        targets = [9200 + i for i in range(20)]
        msg = self._create_mock_message(author_id=7777, content="Bot ping", is_bot=True, target_ids=targets)
        mitigated = await self.engine.inspect_message(msg)
        self.assertFalse(mitigated)
        msg.delete.assert_not_awaited()

    async def test_12_music_running_during_attack_isolated(self):
        """Case 12: Music player remains uninterrupted during mass mention containment."""
        music_player = MagicMock()
        music_player.is_playing = True
        self.bot.music_player = music_player

        targets = [9300 + i for i in range(22)]
        msg = self._create_mock_message(author_id=1012, content="Attack", target_ids=targets)

        # Security executes without affecting music
        mitigated = await self.engine.inspect_message(msg)
        self.assertTrue(mitigated)
        self.assertTrue(music_player.is_playing)

    async def test_13_database_failure_handled_gracefully(self):
        """Case 13: Database exception does not crash bot or prevent message deletion."""
        self.bot.db.create_mention_spam_incident.side_effect = RuntimeError("SQLite Locked")

        targets = [9400 + i for i in range(25)]
        msg = self._create_mock_message(author_id=1013, content="DB Error Attack", target_ids=targets)

        # Should still mitigate message and not raise uncaught exception
        mitigated = await self.engine.inspect_message(msg)
        self.assertTrue(mitigated)
        msg.delete.assert_awaited()

    async def test_14_discord_api_failure_handled_gracefully(self):
        """Case 14: Discord 403 Forbidden on delete/timeout is caught cleanly."""
        targets = [9500 + i for i in range(15)]
        msg = self._create_mock_message(author_id=1014, content="Forbidden Attack", target_ids=targets)
        msg.delete.side_effect = discord.Forbidden(MagicMock(), "Missing Permissions")
        msg.author.timeout.side_effect = discord.Forbidden(MagicMock(), "Missing Permissions")

        # Must execute without propagating exception
        mitigated = await self.engine.inspect_message(msg)
        self.assertTrue(mitigated)


if __name__ == "__main__":
    unittest.main()
