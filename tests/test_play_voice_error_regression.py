"""
Regression test suite for MusicMaid: UnboundLocalError in /play command and Voice Connection Error Handling.
Tests:
1. Voice connection succeeds -> proceeds to search and playback.
2. Voice connection raises an exception -> caught safely without UnboundLocalError.
3. Voice dependency is missing -> formatted and returned with actionable guidance.
4. Voice connection times out -> formatted and returned with timeout diagnostics.
5. Each conditional branch that formats voice connection error (permissions, Voice connection failed, generic).
6. The exception formatter itself encounters an error -> fallback embed rendered safely.
7. /play returns a valid error response without any UnboundLocalError.
8. Discord interactions are acknowledged only once.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import discord
import pytest

from music_bot.commands.music_cog import MusicCog
from music_bot.database.models import QueuedTrack
from music_bot.services.session_service import GuildMusicSession, LoopMode, PlaybackState


@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.session_manager = MagicMock()
    session = GuildMusicSession(guild_id=123456789)
    bot.session_manager.get_session = AsyncMock(return_value=session)
    bot.db = AsyncMock()
    return bot, session


@pytest.fixture
def mock_interaction():
    inter = MagicMock(spec=discord.Interaction)
    inter.guild_id = 123456789
    inter.guild = MagicMock(spec=discord.Guild)
    inter.guild.id = 123456789
    inter.guild.me = MagicMock(spec=discord.Member)

    user = MagicMock(spec=discord.Member)
    user.id = 987654321
    user.display_name = "TestUser"
    user.voice = MagicMock()
    user.voice.channel = MagicMock(spec=discord.VoiceChannel)
    user.voice.channel.id = 555666777
    user.voice.channel.name = "General Voice"
    user.guild_permissions = discord.Permissions.all()

    inter.user = user
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 111222333
    inter.channel = channel

    inter.response = MagicMock()
    inter.response.is_done = MagicMock(return_value=True)
    inter.response.defer = AsyncMock()
    inter.response.send_message = AsyncMock()
    inter.edit_original_response = AsyncMock()
    inter.followup = MagicMock()
    inter.followup.send = AsyncMock()

    return inter


@pytest.mark.asyncio
async def test_play_voice_connection_succeeds(mock_bot, mock_interaction):
    """Test 1: Voice connection succeeds and proceeds to track resolution and playback."""
    bot, session = mock_bot
    cog = MusicCog(bot)

    mock_vc = MagicMock(spec=discord.VoiceClient)
    mock_vc.is_connected = MagicMock(return_value=True)

    fake_track = QueuedTrack(
        title="Kaappaan Hey Amigo",
        url="https://youtube.com/watch?v=mock123",
        duration=240,
        stream_url="https://audio.stream/mock.mp3",
        artist="Harris Jayaraj",
        requester_id=mock_interaction.user.id,
        requester_name="TestUser",
    )

    with patch("music_bot.commands.music_cog.VoiceManager.join_voice_channel", new_callable=AsyncMock) as mock_join, \
         patch("music_bot.commands.music_cog.AudioResolver.resolve_track", new_callable=AsyncMock) as mock_resolve, \
         patch("music_bot.commands.music_cog.MusicPlayerService.start_playback", new_callable=AsyncMock) as mock_start, \
         patch("music_bot.commands.music_cog.MusicPlayerService.build_now_playing_embed", return_value=discord.Embed(title="Now Playing")):

        mock_join.return_value = mock_vc
        mock_resolve.return_value = fake_track
        mock_start.return_value = True

        await cog._play_query(mock_interaction, "Kaappaan Hey Amigo")

        mock_join.assert_awaited_once()
        mock_resolve.assert_awaited_once()
        mock_start.assert_awaited_once()
        mock_interaction.edit_original_response.assert_awaited()
        # Verify no UnboundLocalError occurred
        assert session.last_error is None or "UnboundLocalError" not in str(session.last_error)


@pytest.mark.asyncio
async def test_play_voice_connection_raises_exception(mock_bot, mock_interaction):
    """Test 2: VoiceManager.join_voice_channel raises an unexpected Exception."""
    bot, session = mock_bot
    cog = MusicCog(bot)

    with patch("music_bot.commands.music_cog.VoiceManager.join_voice_channel", new_callable=AsyncMock) as mock_join:
        mock_join.side_effect = RuntimeError("Voice UDP socket failed to bind")

        await cog._play_query(mock_interaction, "kalyani song")

        mock_interaction.edit_original_response.assert_awaited_once()
        call_kwargs = mock_interaction.edit_original_response.call_args.kwargs
        embed = call_kwargs.get("embed")
        assert embed is not None
        assert "COULD NOT CONNECT TO VOICE" in embed.title
        assert "Voice UDP socket failed to bind" in embed.description
        assert "UnboundLocalError" not in embed.description


@pytest.mark.asyncio
async def test_play_voice_connection_missing_dependency(mock_bot, mock_interaction):
    """Test 3: Voice connection fails due to missing PyNaCl or davey dependency."""
    bot, session = mock_bot
    cog = MusicCog(bot)

    session.last_error = (
        "Voice connection failed: Missing required voice dependency (davey).\n"
        "• **Failed Stage:** `Voice Dependency Missing (davey)`\n"
        "• **Target Channel:** <#555666777>\n\n"
        "💡 **Recommended Action:**\nInstall `davey>=0.1.0` in the bot hosting environment."
    )

    with patch("music_bot.commands.music_cog.VoiceManager.join_voice_channel", new_callable=AsyncMock) as mock_join:
        mock_join.return_value = None

        await cog._play_query(mock_interaction, "kalyani song")

        mock_interaction.edit_original_response.assert_awaited_once()
        call_kwargs = mock_interaction.edit_original_response.call_args.kwargs
        embed = call_kwargs.get("embed")
        assert embed is not None
        assert "COULD NOT CONNECT TO VOICE" in embed.title
        assert "Missing required voice dependency (davey)" in embed.description
        # Ensure it does NOT misdiagnose as a Discord permission error
        assert "Edit Channel ➔ Permissions" not in embed.description


@pytest.mark.asyncio
async def test_play_voice_connection_timeout(mock_bot, mock_interaction):
    """Test 4: Voice connection times out during handshake."""
    bot, session = mock_bot
    cog = MusicCog(bot)

    session.last_error = (
        "Voice connection failed: Voice connection timed out after 3 attempts (45000ms).\n"
        "• **Failed Stage:** `Gateway & Voice WebSocket Handshake`"
    )

    with patch("music_bot.commands.music_cog.VoiceManager.join_voice_channel", new_callable=AsyncMock) as mock_join:
        mock_join.return_value = None

        await cog._play_query(mock_interaction, "kalyani song")

        mock_interaction.edit_original_response.assert_awaited_once()
        call_kwargs = mock_interaction.edit_original_response.call_args.kwargs
        embed = call_kwargs.get("embed")
        assert embed is not None
        assert "COULD NOT CONNECT TO VOICE" in embed.title
        assert "Voice connection timed out" in embed.description
        assert "Edit Channel ➔ Permissions" not in embed.description


@pytest.mark.asyncio
async def test_play_voice_connection_permission_branch(mock_bot, mock_interaction):
    """Test 5a: Missing permissions branch formats clear actionable advice."""
    bot, session = mock_bot
    cog = MusicCog(bot)

    session.last_error = "Missing **Connect** permission in <#555666777>"

    with patch("music_bot.commands.music_cog.VoiceManager.join_voice_channel", new_callable=AsyncMock) as mock_join:
        mock_join.return_value = None

        await cog._play_query(mock_interaction, "kalyani song")

        mock_interaction.edit_original_response.assert_awaited_once()
        call_kwargs = mock_interaction.edit_original_response.call_args.kwargs
        embed = call_kwargs.get("embed")
        assert embed is not None
        assert "COULD NOT CONNECT TO VOICE" in embed.title
        assert "How to fix" in embed.description
        assert "grant **MusicMaid** the **Connect** & **Speak** permissions" in embed.description
        assert "General Voice" in embed.description


@pytest.mark.asyncio
async def test_play_voice_connection_forbidden_exception_branch(mock_bot, mock_interaction):
    """Test 5b: Direct discord.Forbidden exception is properly classified as permission error."""
    bot, session = mock_bot
    cog = MusicCog(bot)

    forbidden_exc = discord.Forbidden(MagicMock(status=403, reason="Forbidden"), "Missing Permissions")

    with patch("music_bot.commands.music_cog.VoiceManager.join_voice_channel", new_callable=AsyncMock) as mock_join:
        mock_join.side_effect = forbidden_exc

        await cog._play_query(mock_interaction, "kalyani song")

        mock_interaction.edit_original_response.assert_awaited_once()
        call_kwargs = mock_interaction.edit_original_response.call_args.kwargs
        embed = call_kwargs.get("embed")
        assert embed is not None
        assert "COULD NOT CONNECT TO VOICE" in embed.title
        assert "grant **MusicMaid** the **Connect** & **Speak** permissions" in embed.description


@pytest.mark.asyncio
async def test_play_voice_formatter_resilience_on_exception(mock_bot, mock_interaction):
    """Test 6: Exception inside formatter falls back safely to default embed without crash."""
    bot, session = mock_bot
    cog = MusicCog(bot)

    # Cause member.voice to raise an unexpected attribute error when inspecting
    mock_interaction.user.voice = "invalid_string_not_voice_state"
    session.last_error = "Network route dropped"

    with patch("music_bot.commands.music_cog.VoiceManager.join_voice_channel", new_callable=AsyncMock) as mock_join:
        mock_join.return_value = None

        await cog._play_query(mock_interaction, "test query")

        mock_interaction.edit_original_response.assert_awaited_once()
        call_kwargs = mock_interaction.edit_original_response.call_args.kwargs
        embed = call_kwargs.get("embed")
        assert embed is not None
        assert "COULD NOT CONNECT TO VOICE" in embed.title
        assert "Network route dropped" in embed.description


@pytest.mark.asyncio
async def test_play_no_unbound_local_error_on_preflight_none(mock_bot, mock_interaction):
    """Test 7: VoiceManager returns None without raising an exception - verifies no UnboundLocalError."""
    bot, session = mock_bot
    cog = MusicCog(bot)

    session.last_error = "Cannot play music in the server's AFK voice channel."

    with patch("music_bot.commands.music_cog.VoiceManager.join_voice_channel", new_callable=AsyncMock) as mock_join:
        mock_join.return_value = None

        # Should execute cleanly without raising UnboundLocalError
        await cog._play_query(mock_interaction, "tamil melody song")

        mock_interaction.edit_original_response.assert_awaited_once()
        call_kwargs = mock_interaction.edit_original_response.call_args.kwargs
        embed = call_kwargs.get("embed")
        assert embed is not None
        assert "AFK voice channel" in embed.description


@pytest.mark.asyncio
async def test_play_interaction_single_acknowledgment(mock_bot, mock_interaction):
    """Test 8: Discord interaction is acknowledged exactly once and not double-responded."""
    bot, session = mock_bot
    cog = MusicCog(bot)

    # When response is already done, only edit_original_response is called
    mock_interaction.response.is_done.return_value = True
    session.last_error = "Voice connection could not be established."

    with patch("music_bot.commands.music_cog.VoiceManager.join_voice_channel", new_callable=AsyncMock) as mock_join:
        mock_join.return_value = None

        await cog._play_query(mock_interaction, "song")

        assert mock_interaction.edit_original_response.await_count == 1
        assert mock_interaction.response.send_message.await_count == 0
        assert mock_interaction.followup.send.await_count == 0
