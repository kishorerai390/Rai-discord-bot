"""Tests for explicit application-owned custom emoji overrides."""

from unittest.mock import MagicMock

import discord

from music_bot.emojis import EmojiManager


def setup_function():
    EmojiManager._overrides.clear()


def teardown_function():
    EmojiManager._overrides.clear()


def test_application_emoji_tag_is_used_in_message_even_when_not_in_guild_cache():
    bot = MagicMock()
    bot.get_emoji.return_value = None
    EmojiManager.configure({"PLAY": "app:<a:rai_play3d:123456789012345678>"})

    assert EmojiManager.get("PLAY", bot=bot) == "<a:rai_play3d:123456789012345678>"
    bot.get_emoji.assert_not_called()


def test_application_emoji_tag_can_be_used_on_discord_button():
    bot = MagicMock()
    bot.get_emoji.return_value = None
    EmojiManager.configure({"PAUSE": "app:<:rai_pause3d:123456789012345678>"})

    result = EmojiManager.get_button_emoji("PAUSE", bot=bot)

    assert isinstance(result, discord.PartialEmoji)
    assert result.name == "rai_pause3d"
    assert result.id == 123456789012345678
    bot.get_emoji.assert_not_called()


def test_regular_guild_custom_emoji_still_falls_back_when_unavailable():
    bot = MagicMock()
    bot.get_emoji.return_value = None
    EmojiManager.configure({"QUEUE": "<:rai_queue3d:123456789012345678>"})

    assert EmojiManager.get("QUEUE", bot=bot) == "📜"
    assert EmojiManager.get_button_emoji("QUEUE", bot=bot) == "📜"


def test_invalid_application_emoji_falls_back_safely():
    bot = MagicMock()
    EmojiManager.configure({"PLAY": "app:not-an-emoji"})

    assert EmojiManager.get("PLAY", bot=bot) == "▶️"
    assert EmojiManager.get_button_emoji("PLAY", bot=bot) == "▶️"
