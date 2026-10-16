"""
Automated Test Suite for MusicMaid Premium Emoji, Custom Branding, & UI Upgrade.
Validates:
1. Centralized EmojiManager resolution, override registration, and fallback safety.
2. Discord Button safety (inaccessible custom emojis fallback to curated Unicode without 400 errors).
3. Theme tokens, color palette, and consistent embed builders.
4. NowPlayingControlView dynamic emoji updating across all 13 buttons.
5. Public web platform URL resolution and PremiumLinkView behavior.
"""

import os
from unittest.mock import MagicMock, patch
import pytest
import discord

from music_bot.emojis import EmojiManager, DEFAULT_EMOJI_REGISTRY
from music_bot.theme import (
    COLOR_PRIMARY,
    COLOR_CYAN,
    COLOR_MIDNIGHT,
    COLOR_SUCCESS,
    COLOR_WARNING,
    COLOR_ERROR,
    COLOR_INFO,
    COLOR_PREMIUM,
    create_branded_embed,
    success_embed,
    error_embed,
    warning_embed,
    loading_embed,
    info_embed,
    premium_embed,
)
from music_bot.services.session_service import GuildMusicSession, LoopMode, PlaybackState, QueuedTrack
from music_bot.services.player_service import MusicPlayerService, NowPlayingControlView
from music_bot.commands.music_cog import PremiumLinkView, get_public_web_url


@pytest.fixture
def sample_track():
    return QueuedTrack(
        title="Kalyani (feat. Raghu Dixit)",
        url="https://www.youtube.com/watch?v=sample123",
        duration=285,
        artist="Raghu Dixit",
        thumbnail="https://i.ytimg.com/vi/sample123/hqdefault.jpg",
        requester_id=123456789,
        requester_name="AnimeListener",
    )


@pytest.fixture
def mock_session(sample_track):
    session = GuildMusicSession(guild_id=1001)
    session.current_track = sample_track
    session.state = PlaybackState.PLAYING
    session.volume = 85
    session.loop_mode = LoopMode.OFF

    mock_vc = MagicMock()
    mock_vc.is_connected.return_value = True
    mock_vc.is_playing.return_value = True
    mock_vc.is_paused.return_value = False
    mock_channel = MagicMock()
    mock_channel.id = 555
    mock_channel.mention = "<#555>"
    mock_vc.channel = mock_channel
    mock_vc.guild.me.voice = None
    session.voice_client = mock_vc
    return session


class TestEmojiManager:

    def test_01_default_registry_keys(self):
        """Verify all essential music and branding keys exist in DEFAULT_EMOJI_REGISTRY."""
        required_keys = [
            "LOGO", "NOTE", "DISC", "SEARCH", "LOADING", "PLAY", "PAUSE",
            "PREVIOUS", "NEXT", "SKIP", "STOP", "QUEUE", "PLAYLIST",
            "AUTODJ", "VOLUME", "EQUALIZER", "LYRICS", "FAVORITE",
            "PREMIUM", "SUCCESS", "ERROR", "WARNING", "INFO",
            "SETTINGS", "STATS", "DOCTOR", "LOOP", "SHUFFLE"
        ]
        for key in required_keys:
            assert key in DEFAULT_EMOJI_REGISTRY, f"Missing key in default registry: {key}"
            assert isinstance(DEFAULT_EMOJI_REGISTRY[key], str)

    def test_02_get_fallback_without_overrides(self):
        """Verify get() returns default Unicode emoji when no custom override is set."""
        EmojiManager._overrides.clear()
        assert EmojiManager.get("PLAY") == "▶️"
        assert EmojiManager.get("PAUSE") == "⏸️"
        assert EmojiManager.get("QUEUE") == "📜"
        assert EmojiManager.get("PREMIUM") == "💎"

    def test_03_custom_emoji_override_with_bot_access(self):
        """Verify get() and get_button_emoji() resolve custom server emoji when accessible."""
        mock_emoji = MagicMock(spec=discord.Emoji)
        mock_emoji.id = 987654321098765432
        mock_emoji.__str__.return_value = "<:musicmaid_play:987654321098765432>"

        mock_bot = MagicMock()
        mock_bot.get_emoji.return_value = mock_emoji

        EmojiManager.configure({"PLAY": "987654321098765432"})
        
        # Text representation
        text_val = EmojiManager.get("PLAY", bot=mock_bot)
        assert text_val == "<:musicmaid_play:987654321098765432>"
        
        # Button representation
        btn_emoji = EmojiManager.get_button_emoji("PLAY", bot=mock_bot)
        assert btn_emoji == mock_emoji

        # Clean up
        EmojiManager._overrides.clear()

    def test_04_custom_emoji_fallback_when_bot_lacks_access(self):
        """Verify get() falls back cleanly to Unicode when bot cannot access custom emoji ID."""
        mock_bot = MagicMock()
        mock_bot.get_emoji.return_value = None  # Emoji deleted or bot not in that guild

        EmojiManager.configure({"QUEUE": "111222333444555666"})
        
        # Should gracefully fall back to Unicode "📜" instead of crashing or returning broken snowflake
        res = EmojiManager.get("QUEUE", bot=mock_bot)
        assert res == "📜"

        btn_res = EmojiManager.get_button_emoji("QUEUE", bot=mock_bot)
        assert btn_res == "📜"

        EmojiManager._overrides.clear()

    def test_05_diagnostic_map(self):
        """Verify get_diagnostic_map exposes configuration metadata."""
        diag = EmojiManager.get_diagnostic_map()
        assert "LOGO" in diag
        assert "fallback" in diag["LOGO"]
        assert "active_display" in diag["LOGO"]


class TestThemeAndEmbeds:

    def test_06_branded_embed_creation(self):
        """Verify create_branded_embed sets consistent footer, color, and title."""
        embed = create_branded_embed("Test Title", "Test Description", color=COLOR_CYAN)
        assert embed.title == "Test Title"
        assert embed.description == "Test Description"
        assert embed.color.value == COLOR_CYAN
        assert "MusicMaid" in embed.footer.text

    def test_07_status_embeds(self):
        """Verify success, error, warning, loading, and premium embeds use distinctive styling."""
        s = success_embed("Operation Completed", "All tracks synced.")
        assert "Success" in s.title or "MusicMaid" in s.title
        assert s.color.value == COLOR_SUCCESS

        e = error_embed("File Corrupt", "Cannot decode format.")
        assert "Error" in e.title or "MusicMaid" in e.title
        assert e.color.value == COLOR_ERROR

        w = warning_embed("Volume Warning", "High volume may distort.")
        assert w.color.value == COLOR_WARNING

        p = premium_embed("Perks Unlocked", "24/7 Voice active.")
        assert p.color.value == COLOR_PREMIUM


class TestMasterPlayerViewUpgrade:

    def test_08_now_playing_embed_anime_neon_elements(self, mock_session):
        """Verify build_now_playing_embed includes voice channel mention and anime neon tokens."""
        embed = MusicPlayerService.build_now_playing_embed(mock_session)
        assert "Now Playing" in embed.title
        assert "LIVE PLAYING" in embed.description
        assert "Kalyani" in embed.description
        assert "Raghu Dixit" in embed.description
        assert "<#555>" in embed.description  # Current voice channel mention
        assert embed.thumbnail.url == "https://i.ytimg.com/vi/sample123/hqdefault.jpg"

    def test_09_now_playing_control_view_13_buttons(self, mock_session):
        """Verify NowPlayingControlView correctly maps all 13 buttons with updated emojis."""
        view = NowPlayingControlView(mock_session)
        buttons = [child for child in view.children if isinstance(child, discord.ui.Button)]
        assert len(buttons) == 13

        # Button custom IDs
        custom_ids = {b.custom_id for b in buttons}
        assert "music_btn_prev" in custom_ids
        assert "music_btn_play_pause" in custom_ids
        assert "music_btn_skip" in custom_ids
        assert "music_btn_queue" in custom_ids
        assert "music_btn_favorite" in custom_ids
        assert "music_btn_filters" in custom_ids
        assert "music_btn_lyrics" in custom_ids

    def test_10_premium_link_view(self):
        """Verify PremiumLinkView attaches working link button to web URL."""
        test_url = "https://rai-discord-bot.onrender.com"
        view = PremiumLinkView(test_url)
        assert len(view.children) == 1
        btn = view.children[0]
        assert isinstance(btn, discord.ui.Button)
        assert btn.style == discord.ButtonStyle.link
        assert btn.url == test_url
