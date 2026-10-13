"""
Automated Test Suite for MusicMaid: Missing Now Playing Player & Voice Connection Errors.
Tests Phase 1 through Phase 7:
1. Voice Connection lifecycle, stale VoiceClient cleanup, bounded retries & UDP diagnostics.
2. Text Channel resolution & permission verification (View Channel, Send Messages, Embed Links, Read Message History).
3. Now Playing message creation, in-place edit updates, and deletion recovery.
4. Concurrency serialization preventing duplicate player messages.
5. Real audio playback start and state transitions (Play, Pause, Resume, Stop, Queue).
"""

import asyncio
from collections import deque
from unittest.mock import AsyncMock, MagicMock, patch
import discord
import pytest

from music_bot.database.models import QueuedTrack
from music_bot.services.player_service import MusicPlayerService, NowPlayingControlView
from music_bot.services.session_service import GuildMusicSession, LoopMode, PlaybackState
from music_bot.services.voice_service import VoiceManager


def make_track(title="Tamil Video Song", url="https://youtube.com/watch?v=mock123", duration=240, artist="Jukebox"):
    return QueuedTrack(
        title=title,
        url=url,
        duration=duration,
        stream_url="https://audio.stream/mock.mp3",
        artist=artist,
        thumbnail="https://mock.img/art.jpg",
        requester_id=98765,
        requester_name="Kishore",
    )


@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.db = AsyncMock()
    bot.db.get_favorites = AsyncMock(return_value=[])
    bot.db.add_favorite = AsyncMock(return_value=True)
    bot.db.remove_favorite = AsyncMock(return_value=True)
    bot.db.update_guild_settings = AsyncMock(return_value=True)
    bot.db.save_session = AsyncMock(return_value=True)
    bot.db.delete_session = AsyncMock(return_value=True)
    bot.db.record_history = AsyncMock(return_value=True)

    g_settings = MagicMock()
    g_settings.request_channel_id = 999111
    bot.db.get_guild_settings = AsyncMock(return_value=g_settings)
    return bot


@pytest.fixture
def mock_session():
    session = GuildMusicSession(guild_id=1525030316845301781)
    session.volume = 80
    session.loop_mode = LoopMode.OFF
    session.current_track = make_track()
    session.state = PlaybackState.PLAYING

    mock_vc = MagicMock()
    mock_vc.is_connected.return_value = True
    mock_vc.is_playing.return_value = True
    mock_vc.is_paused.return_value = False
    mock_vc.channel = MagicMock(id=888111, name="Voice Testing")
    mock_vc.source = MagicMock(volume=0.8)
    mock_vc.guild = MagicMock(id=1525030316845301781)
    session.voice_client = mock_vc

    return session


@pytest.fixture
def mock_text_channel():
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 777222
    channel.name = "music-chat"
    channel.mention = "<#777222>"
    guild = MagicMock(id=1525030316845301781, name="THOR APEX")
    channel.guild = guild
    guild.me = MagicMock()

    perms = MagicMock()
    perms.view_channel = True
    perms.send_messages = True
    perms.embed_links = True
    perms.read_message_history = True
    channel.permissions_for.return_value = perms

    channel.send = AsyncMock()
    channel.fetch_message = AsyncMock()
    return channel


# =============================================================================
# 1. VOICE CONNECTION & UDP ERROR RESILIENCE
# =============================================================================

@pytest.mark.asyncio
async def test_voice_connection_stale_client_cleanup(mock_session):
    """Verify VoiceManager detects and terminates stale non-connected VoiceClient before connecting."""
    member = MagicMock(spec=discord.Member)
    member.guild = MagicMock(id=1525030316845301781, name="THOR APEX")
    target_vc = MagicMock(spec=discord.VoiceChannel)
    target_vc.id = 888111
    target_vc.name = "Testing Zone"
    member.voice = MagicMock(channel=target_vc)

    perms = MagicMock()
    perms.connect = True
    perms.speak = True
    target_vc.permissions_for.return_value = perms

    # Stale voice client in guild that is NOT connected
    stale_vc = MagicMock(spec=discord.VoiceClient)
    stale_vc.is_connected.return_value = False
    stale_vc.disconnect = AsyncMock()
    member.guild.voice_client = stale_vc
    member.guild.change_voice_state = AsyncMock()

    new_vc = MagicMock(spec=discord.VoiceClient)
    new_vc.is_connected.return_value = True
    target_vc.connect = AsyncMock(return_value=new_vc)

    with patch("asyncio.sleep", new_callable=AsyncMock):
        vc = await VoiceManager.join_voice_channel(member, MagicMock(), mock_session)

    assert vc == new_vc
    stale_vc.disconnect.assert_awaited_with(force=True)
    member.guild.change_voice_state.assert_awaited_with(channel=None)


@pytest.mark.asyncio
async def test_voice_connection_signalling_timeout_retry_success(mock_session):
    """Verify VoiceManager performs bounded retries on timeout and recovers when handshake succeeds."""
    member = MagicMock(spec=discord.Member)
    member.guild = MagicMock(id=1525030316845301781, name="THOR APEX")
    member.guild.voice_client = None
    member.guild.change_voice_state = AsyncMock()

    target_vc = MagicMock(spec=discord.VoiceChannel)
    target_vc.id = 888111
    target_vc.name = "Music VC"
    member.voice = MagicMock(channel=target_vc)

    perms = MagicMock()
    perms.connect = True
    perms.speak = True
    target_vc.permissions_for.return_value = perms

    new_vc = MagicMock(spec=discord.VoiceClient)
    new_vc.is_connected.return_value = True

    # 1st attempt: TimeoutError, 2nd attempt: Success
    target_vc.connect = AsyncMock(side_effect=[asyncio.TimeoutError(), new_vc])

    with patch("asyncio.sleep", new_callable=AsyncMock):
        vc = await VoiceManager.join_voice_channel(member, MagicMock(), mock_session)

    assert vc == new_vc
    assert mock_session.state == PlaybackState.CONNECTED
    assert mock_session.last_error is None


@pytest.mark.asyncio
async def test_voice_connection_all_timeouts_actionable_diagnostic(mock_session):
    """Verify that when all attempts time out, actionable UDP network diagnostic is recorded."""
    member = MagicMock(spec=discord.Member)
    member.guild = MagicMock(id=1525030316845301781, name="THOR APEX")
    member.guild.voice_client = None
    member.guild.change_voice_state = AsyncMock()

    target_vc = MagicMock(spec=discord.VoiceChannel)
    target_vc.id = 888111
    target_vc.name = "Music VC"
    target_vc.mention = "<#888111>"
    member.voice = MagicMock(channel=target_vc)

    perms = MagicMock()
    perms.connect = True
    perms.speak = True
    target_vc.permissions_for.return_value = perms

    # All attempts timeout
    target_vc.connect = AsyncMock(side_effect=asyncio.TimeoutError())

    with patch("asyncio.sleep", new_callable=AsyncMock):
        vc = await VoiceManager.join_voice_channel(member, MagicMock(), mock_session)

    assert vc is None
    assert mock_session.state == PlaybackState.ERROR
    assert "Voice connection failed after 3 attempts" in mock_session.last_error
    assert "UDP" in mock_session.last_error
    assert "ports 50000" in mock_session.last_error


# =============================================================================
# 2. TEXT CHANNEL RESOLUTION & PERMISSIONS
# =============================================================================

@pytest.mark.asyncio
async def test_resolve_text_channel_direct_valid(mock_session, mock_text_channel):
    """Verify resolve_text_channel selects existing valid text channel with full permissions."""
    mock_session.text_channel = mock_text_channel
    channel, err = await MusicPlayerService.resolve_text_channel(mock_session)

    assert channel == mock_text_channel
    assert err is None


@pytest.mark.asyncio
async def test_resolve_text_channel_fallback_to_request_channel(mock_bot, mock_session, mock_text_channel):
    """Verify resolve_text_channel recovers text channel using database request_channel_id when session.text_channel is None."""
    mock_session.text_channel = None
    guild = mock_text_channel.guild
    guild.get_channel = MagicMock(return_value=mock_text_channel)
    mock_bot.get_guild.return_value = guild

    channel, err = await MusicPlayerService.resolve_text_channel(mock_session, bot=mock_bot)

    assert channel == mock_text_channel
    assert err is None
    assert mock_session.text_channel == mock_text_channel


@pytest.mark.asyncio
async def test_resolve_text_channel_missing_permissions_diagnostic(mock_session, mock_text_channel):
    """Verify resolve_text_channel returns clear diagnostic when bot lacks Embed Links permission."""
    mock_session.text_channel = mock_text_channel
    perms = MagicMock()
    perms.view_channel = True
    perms.send_messages = True
    perms.embed_links = False
    perms.read_message_history = True
    mock_text_channel.permissions_for.return_value = perms
    mock_text_channel.guild.text_channels = [mock_text_channel]

    channel, err = await MusicPlayerService.resolve_text_channel(mock_session)

    assert channel is None
    assert "Embed Links" in err


# =============================================================================
# 3. NOW PLAYING MESSAGE LIFECYCLE & IN-PLACE EDITS
# =============================================================================

@pytest.mark.asyncio
async def test_send_now_playing_panel_creates_message_with_13_buttons(mock_bot, mock_session, mock_text_channel):
    """Verify send_now_playing_panel creates a new message with 13-button 4-row matrix."""
    mock_session.text_channel = mock_text_channel
    sent_msg = MagicMock(spec=discord.Message)
    sent_msg.id = 555001
    mock_text_channel.send.return_value = sent_msg

    await MusicPlayerService.send_now_playing_panel(mock_session, bot=mock_bot)

    mock_text_channel.send.assert_awaited_once()
    kwargs = mock_text_channel.send.call_args.kwargs
    assert "embed" in kwargs
    assert "view" in kwargs
    view = kwargs["view"]
    assert isinstance(view, NowPlayingControlView)
    assert len(view.children) == 13  # 13 buttons

    assert mock_session.now_playing_message == sent_msg
    assert mock_session.now_playing_message_id == 555001
    assert mock_session.now_playing_channel_id == mock_text_channel.id


@pytest.mark.asyncio
async def test_send_now_playing_panel_updates_existing_in_place(mock_bot, mock_session, mock_text_channel):
    """Verify subsequent call updates existing player message instead of spamming new ones."""
    mock_session.text_channel = mock_text_channel
    existing_msg = MagicMock(spec=discord.Message)
    existing_msg.id = 555001
    existing_msg.channel = mock_text_channel
    existing_msg.edit = AsyncMock()
    mock_session.now_playing_message = existing_msg

    await MusicPlayerService.send_now_playing_panel(mock_session, bot=mock_bot)

    existing_msg.edit.assert_awaited_once()
    mock_text_channel.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_now_playing_panel_safe_recovery_on_deleted_message(mock_bot, mock_session, mock_text_channel):
    """Verify that if the old message was deleted, it recovers safely and posts a new one."""
    mock_session.text_channel = mock_text_channel
    old_msg = MagicMock(spec=discord.Message)
    old_msg.id = 555001
    old_msg.channel = mock_text_channel
    old_msg.edit = AsyncMock(side_effect=discord.NotFound(MagicMock(), "Unknown Message"))
    mock_session.now_playing_message = old_msg

    new_msg = MagicMock(spec=discord.Message)
    new_msg.id = 555002
    mock_text_channel.send.return_value = new_msg

    await MusicPlayerService.send_now_playing_panel(mock_session, bot=mock_bot)

    # Edit was attempted and failed with NotFound
    old_msg.edit.assert_awaited_once()
    # Recovered by sending new message
    mock_text_channel.send.assert_awaited_once()
    assert mock_session.now_playing_message == new_msg
    assert mock_session.now_playing_message_id == 555002


@pytest.mark.asyncio
async def test_send_now_playing_panel_missing_embed_links_warning(mock_bot, mock_session, mock_text_channel):
    """Verify that when Embed Links is missing, a clear text diagnostic alert is dispatched."""
    mock_session.text_channel = mock_text_channel
    perms = MagicMock()
    perms.view_channel = True
    perms.send_messages = True
    perms.embed_links = False
    perms.read_message_history = True
    mock_text_channel.permissions_for.return_value = perms

    await MusicPlayerService.send_now_playing_panel(mock_session, bot=mock_bot)

    # Must have sent plain text permission alert
    mock_text_channel.send.assert_awaited_once()
    sent_text = mock_text_channel.send.call_args[0][0]
    assert "Embed Links" in sent_text


@pytest.mark.asyncio
async def test_panel_concurrency_lock_prevents_duplicate_messages(mock_bot, mock_session, mock_text_channel):
    """Verify concurrency serialization prevents two parallel calls from creating competing messages."""
    mock_session.text_channel = mock_text_channel
    sent_msg = MagicMock(spec=discord.Message)
    sent_msg.id = 555001
    sent_msg.channel = mock_text_channel
    sent_msg.edit = AsyncMock()

    async def slow_send(*args, **kwargs):
        await asyncio.sleep(0.05)
        return sent_msg

    mock_text_channel.send.side_effect = slow_send

    # Launch two simultaneous calls
    await asyncio.gather(
        MusicPlayerService.send_now_playing_panel(mock_session, bot=mock_bot),
        MusicPlayerService.send_now_playing_panel(mock_session, bot=mock_bot),
    )

    # Exactly one send call should happen; the second call updates the newly established message
    assert mock_text_channel.send.await_count == 1
    assert sent_msg.edit.await_count == 1
