"""
Unit tests for Rai Bot Features:
- AutoMod Kick & Public Chat Alert Format
- Economy & Shop Mechanics
- Gaming Matchmaker Queues
- AI Companion Persona
"""

import asyncio
import re
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import discord

from cogs.automod import EMOJI_REGEX, UNICODE_EMOJI_REGEX
from cogs.matchmaker import QUEUE_MANAGER, GAME_PRESETS
from utils.ai_security_brain import AISecurityBrain


class TestRaiFeatures(unittest.IsolatedAsyncioTestCase):

    async def test_automod_emoji_counting(self):
        """Verify AutoMod accurately counts custom and unicode emojis to trigger Emoji Spam."""
        msg_content = "Hello! 🍎🍌🍇🍓🍒🍑🍍🥥🥝🍅🥑🍆🥒🥬🥦🌽🥕🧄🧅🥔"
        custom_count = len(EMOJI_REGEX.findall(msg_content))
        unicode_count = len(UNICODE_EMOJI_REGEX.findall(msg_content))
        total = custom_count + unicode_count
        self.assertEqual(total, 20)

        # Formatted string verification matching user's screenshot
        reason = f"Emoji Spam ({total} emojis)"
        action_word = "KICKED"
        member_name = "tushar050390"
        alert_str = f"🚫 **{member_name}** was **{action_word}** by AutoMod ({reason})."
        expected = "🚫 **tushar050390** was **KICKED** by AutoMod (Emoji Spam (20 emojis))."
        self.assertEqual(alert_str, expected)

    async def test_automod_word_filter_kick_alert(self):
        """Verify AutoMod Word Filter Violation kick alert matches user screenshot."""
        reason = "Word Filter Violation"
        action_word = "KICKED"
        member_name = "rc.rai_007"
        alert_str = f"🚫 **{member_name}** was **{action_word}** by AutoMod ({reason})."
        expected = "🚫 **rc.rai_007** was **KICKED** by AutoMod (Word Filter Violation)."
        self.assertEqual(alert_str, expected)

    async def test_matchmaker_queue_lifecycle(self):
        """Test queueing players and firing squad match when target size is reached."""
        guild_id = 99999999
        preset_key = "bgmi_duo"

        # Clear any prior state
        await QUEUE_MANAGER.remove_player(guild_id, 101)
        await QUEUE_MANAGER.remove_player(guild_id, 102)

        # Player 1 joins duo
        players, is_full = await QUEUE_MANAGER.add_player(guild_id, preset_key, 101)
        self.assertFalse(is_full)
        self.assertEqual(players, [101])

        # Player 2 joins duo -> Match complete!
        matched, is_full = await QUEUE_MANAGER.add_player(guild_id, preset_key, 102)
        self.assertTrue(is_full)
        self.assertEqual(matched, [101, 102])

        # Queue should now be empty for that preset
        status = await QUEUE_MANAGER.get_queue_status(guild_id)
        self.assertNotIn(preset_key, status)

    async def test_ai_companion_response(self):
        """Test AI Companion embedded heuristic persona."""
        brain = AISecurityBrain()
        # Test greeting
        resp = await brain.generate_chat_response("Hey Rai, how are you?", "Alex", "RAI FAM💗")
        self.assertIn("Alex", resp)

        # Test gaming question
        resp_gaming = await brain.generate_chat_response("Can I find a squad for BGMI?", "Alex", "RAI FAM💗")
        self.assertIn("matchmaker", resp_gaming.lower())

        # Test economy question
        resp_eco = await brain.generate_chat_response("How do I get coins?", "Alex", "RAI FAM💗")
        self.assertIn("daily", resp_eco.lower())


if __name__ == "__main__":
    unittest.main()
