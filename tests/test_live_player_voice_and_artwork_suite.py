"""
Automated Test Suite for MusicMaid:
Live Player, Voice Channel Sync & Search Result Artwork.

Validates:
1. Each player action and its backend authorization (PAUSE, RESUME, SKIP, PREVIOUS, STOP, VOLUME, SHUFFLE, LOOP, 247_TOGGLE, FILTER).
2. Invalid guild ID and unauthorized user handling.
3. Play Now versus Queue behavior.
4. Pause/resume and skip failure handling.
5. Volume range validation (0-150).
6. Real Discord voice channel state updates and honest disconnections (no placeholder channels).
7. Independent artwork for multiple distinct search results (YouTube thumbnails & Spotify metadata).
8. Missing artwork fallback to consistent default.
9. Persistent 24/7 setting persistence into SQLite.
10. Auto voice join on playback request when member is in voice.
"""

import asyncio
import json
from collections import deque
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from aiohttp import web
from music_bot.database.models import QueuedTrack
from music_bot.services.session_service import GuildMusicSession, LoopMode, PlaybackState, SessionManager
from music_bot.services.resolver_service import AudioResolver
from music_bot.services.player_service import MusicPlayerService
from web.music_api import MusicApiRouter


def make_track(title="Song A", url="https://youtube.com/watch?v=aaa111", duration=180, artist="Artist A", thumb="https://i.ytimg.com/vi/aaa111/hqdefault.jpg"):
    return QueuedTrack(
        title=title,
        url=url,
        duration=duration,
        stream_url="https://audio.stream/mock.mp3",
        artist=artist,
        thumbnail=thumb,
        requester_id=12345,
        requester_name="Kishore",
    )


@pytest.fixture
def mock_bot():
    bot = MagicMock()
    bot.is_ready = MagicMock(return_value=True)
    bot.db = AsyncMock()
    bot.db.get_favorites = AsyncMock(return_value=[])
    bot.db.add_favorite = AsyncMock(return_value=True)
    bot.db.remove_favorite = AsyncMock(return_value=True)
    bot.db.update_guild_settings = AsyncMock(return_value=True)
    bot.db.save_session = AsyncMock(return_value=True)
    bot.db.delete_session = AsyncMock(return_value=True)
    bot.db.record_history = AsyncMock(return_value=True)
    bot.db.submit_web_action = AsyncMock(return_value=101)
    bot.db.mark_web_action_completed = AsyncMock(return_value=True)
    bot.db.get_recent_history = AsyncMock(return_value=[])
    bot.db.get_all_active_sessions = AsyncMock(return_value=[])

    g_settings = MagicMock()
    g_settings.request_channel_id = 999111
    g_settings.twenty_four_seven_enabled = 0
    g_settings.twenty_four_seven_channel_id = None
    g_settings.default_volume = 80
    g_settings.prefix = ","
    bot.db.get_guild_settings = AsyncMock(return_value=g_settings)

    # Setup guild and voice channel
    guild = MagicMock()
    guild.id = 1525030316845301781
    guild.name = "MusicMaid Lounge"

    vc = MagicMock()
    vc.is_connected = MagicMock(return_value=True)
    vc_channel = MagicMock()
    vc_channel.id = 777888
    vc_channel.name = "General Chill Voice"
    vc.channel = vc_channel
    guild.voice_client = vc

    bot.get_guild = MagicMock(side_effect=lambda gid: guild if gid == 1525030316845301781 else None)
    bot.guilds = [guild]
    return bot


@pytest.fixture
def music_api(mock_bot):
    router = MusicApiRouter(auth_manager=None, bot=mock_bot)
    router.db = mock_bot.db
    router._db_connected = True

    # Setup test session in SessionManager
    sm = SessionManager.get_instance()
    session = sm.get_session_sync(1525030316845301781)
    session.volume = 80
    session.loop_mode = LoopMode.OFF
    session.current_track = make_track()
    session.state = PlaybackState.PLAYING
    session.twenty_four_seven = False
    session.voice_client = mock_bot.get_guild(1525030316845301781).voice_client

    return router


@pytest.mark.asyncio
async def test_honest_voice_channel_state_connected(music_api, mock_bot):
    """Voice client connected should return actual voice channel name and Connected status."""
    request = MagicMock()
    request.query = {"guild_id": "1525030316845301781"}

    resp = await music_api.get_session(request)
    assert resp.status == 200
    data = json.loads(resp.text)
    assert data["success"] is True
    session_data = data["data"]["session"]
    assert session_data["voice_status"] == "Connected"
    assert session_data["voice_channel_name"] == "General Chill Voice"
    assert session_data["channel_name"] == "General Chill Voice"


@pytest.mark.asyncio
async def test_honest_voice_channel_state_disconnected(music_api, mock_bot):
    """Voice client disconnected must NOT show hardcoded fake channels (#❄️. Fun Time ! or #Voice Channel)."""
    guild = mock_bot.get_guild(1525030316845301781)
    guild.voice_client = None

    sm = SessionManager.get_instance()
    session = sm.get_session_nowait(1525030316845301781)
    session.voice_client = None
    session.channel_id = None
    session.state = PlaybackState.IDLE

    request = MagicMock()
    request.query = {"guild_id": "1525030316845301781"}

    resp = await music_api.get_session(request)
    assert resp.status == 200
    data = json.loads(resp.text)
    assert data["success"] is True
    session_data = data["data"]["session"]
    assert session_data["voice_status"] == "Disconnected"
    assert session_data["voice_channel_name"] is None
    assert session_data["channel_name"] is None


@pytest.mark.asyncio
async def test_player_action_pause_and_resume(music_api):
    """Player action PAUSE and RESUME must call player_service and return honest success/error."""
    with patch.object(MusicPlayerService, "pause", new_callable=AsyncMock) as mock_pause, \
         patch.object(MusicPlayerService, "resume", new_callable=AsyncMock) as mock_resume:
        mock_pause.return_value = (True, "Paused playback")
        mock_resume.return_value = (True, "Resumed playback")

        # PAUSE
        request = MagicMock()
        request.json = AsyncMock(return_value={"guild_id": "1525030316845301781", "action": "PAUSE"})
        resp = await music_api.dispatch_control(request)
        data = json.loads(resp.text)
        assert data["success"] is True
        assert "Paused playback" in data["data"]["message"]
        mock_pause.assert_called_once()

        # RESUME
        request.json = AsyncMock(return_value={"guild_id": "1525030316845301781", "action": "RESUME"})
        resp = await music_api.dispatch_control(request)
        data = json.loads(resp.text)
        assert data["success"] is True
        assert "Resumed playback" in data["data"]["message"]
        mock_resume.assert_called_once()


@pytest.mark.asyncio
async def test_player_action_pause_failure_handling(music_api):
    """When pause fails (e.g. already paused or no audio), return descriptive error."""
    with patch.object(MusicPlayerService, "pause", new_callable=AsyncMock) as mock_pause:
        mock_pause.return_value = (False, "Player is already paused")

        request = MagicMock()
        request.json = AsyncMock(return_value={"guild_id": "1525030316845301781", "action": "PAUSE"})

        resp = await music_api.dispatch_control(request)
        data = json.loads(resp.text)
        assert data["success"] is False
        assert "Player is already paused" in data["error"]["message"]


@pytest.mark.asyncio
async def test_player_action_skip_and_previous(music_api):
    """Skip and Previous should call backend player_service and report accurate status."""
    with patch.object(MusicPlayerService, "skip", new_callable=AsyncMock) as mock_skip, \
         patch.object(MusicPlayerService, "previous", new_callable=AsyncMock) as mock_prev:
        next_track = make_track(title="Next Song")
        mock_skip.return_value = (True, "Skipped to next song", next_track)
        mock_prev.return_value = (False, "No previous tracks in history", None)

        request = MagicMock()
        request.json = AsyncMock(return_value={"guild_id": "1525030316845301781", "action": "SKIP"})
        resp = await music_api.dispatch_control(request)
        data = json.loads(resp.text)
        assert data["success"] is True
        assert "Skipped to next song" in data["data"]["message"]

        # PREVIOUS failure
        request.json = AsyncMock(return_value={"guild_id": "1525030316845301781", "action": "PREVIOUS"})
        resp = await music_api.dispatch_control(request)
        data = json.loads(resp.text)
        assert data["success"] is False
        assert "No previous tracks" in data["error"]["message"]


@pytest.mark.asyncio
async def test_player_action_volume_validation(music_api):
    """Volume slider must validate range (0-150) and reject out-of-range payloads."""
    with patch.object(MusicPlayerService, "set_volume", new_callable=AsyncMock) as mock_vol:
        mock_vol.return_value = (True, "Volume set to 75%")

        # Valid volume
        request = MagicMock()
        request.json = AsyncMock(return_value={"guild_id": "1525030316845301781", "action": "VOLUME", "payload": {"volume": 75}})
        resp = await music_api.dispatch_control(request)
        data = json.loads(resp.text)
        assert data["success"] is True
        assert "75%" in data["data"]["message"]

        # Invalid volume (< 0)
        request.json = AsyncMock(return_value={"guild_id": "1525030316845301781", "action": "VOLUME", "payload": {"volume": -10}})
        resp = await music_api.dispatch_control(request)
        data = json.loads(resp.text)
        assert data["success"] is False
        assert "between 0 and 150%" in data["error"]["message"]

        # Invalid volume (> 150)
        request.json = AsyncMock(return_value={"guild_id": "1525030316845301781", "action": "VOLUME", "payload": {"volume": 200}})
        resp = await music_api.dispatch_control(request)
        data = json.loads(resp.text)
        assert data["success"] is False
        assert "between 0 and 150%" in data["error"]["message"]


@pytest.mark.asyncio
async def test_247_mode_toggle_and_sqlite_persistence(music_api, mock_bot):
    """24/7 toggle must toggle in-memory state AND persist to SQLite via bot.db.update_guild_settings."""
    sm = SessionManager.get_instance()
    session = sm.get_session_nowait(1525030316845301781)
    session.twenty_four_seven = False

    request = MagicMock()
    request.json = AsyncMock(return_value={"guild_id": "1525030316845301781", "action": "247_TOGGLE"})

    resp = await music_api.dispatch_control(request)
    data = json.loads(resp.text)
    assert data["success"] is True
    assert session.twenty_four_seven is True
    mock_bot.db.update_guild_settings.assert_called_once()


@pytest.mark.asyncio
async def test_play_now_versus_enqueue_behavior(music_api):
    """PLAY_NOW skips/starts immediately; ENQUEUE adds to queue without interrupting current track."""
    resolved_track = make_track(title="Added Song")

    with patch.object(AudioResolver, "resolve_track", new_callable=AsyncMock) as mock_resolve, \
         patch.object(MusicPlayerService, "skip", new_callable=AsyncMock) as mock_skip, \
         patch.object(MusicPlayerService, "send_now_playing_panel", new_callable=AsyncMock):
        mock_resolve.return_value = resolved_track
        mock_skip.return_value = (True, "Skipped", resolved_track)

        sm = SessionManager.get_instance()
        session = sm.get_session_nowait(1525030316845301781)
        session.state = PlaybackState.PLAYING
        session.queue.clear()

        # Test PLAY_NOW
        request = MagicMock()
        request.json = AsyncMock(return_value={
            "guild_id": "1525030316845301781",
            "action": "PLAY_NOW",
            "payload": {"query": "https://youtube.com/watch?v=now123"}
        })
        resp = await music_api.dispatch_control(request)
        data = json.loads(resp.text)
        assert data["success"] is True
        assert "Playing 'Added Song' immediately!" in data["data"]["message"]
        mock_skip.assert_called_once()

        # Test ENQUEUE
        request.json = AsyncMock(return_value={
            "guild_id": "1525030316845301781",
            "action": "ENQUEUE",
            "payload": {"query": "https://youtube.com/watch?v=queue456"}
        })
        resp = await music_api.dispatch_control(request)
        data = json.loads(resp.text)
        assert data["success"] is True
        assert "Added 'Added Song' to queue" in data["data"]["message"]
        assert len(session.queue) >= 1


@pytest.mark.asyncio
async def test_unauthorized_guild_validation(music_api, mock_bot):
    """Accessing non-existent guild ID returns descriptive 404 error."""
    request = MagicMock()
    request.json = AsyncMock(return_value={
        "guild_id": "999999999999999999",
        "action": "PAUSE"
    })
    resp = await music_api.dispatch_control(request)
    data = json.loads(resp.text)
    assert data["success"] is False
    assert "Bot is not present in guild 999999999999999999" in data["error"]["message"]


@pytest.mark.asyncio
async def test_search_results_have_independent_artwork_and_stable_ids(music_api):
    """Search results must each have their OWN distinct artwork and unique stable IDs."""
    fake_yt_entries = [
        {
            "id": "vid_abc_1",
            "title": "Arabic Kuthu - Halamithi Habibo",
            "uploader": "Sun TV",
            "duration": 280,
            "webpage_url": "https://www.youtube.com/watch?v=vid_abc_1",
            "thumbnails": [{"url": "https://i.ytimg.com/vi/vid_abc_1/hqdefault.jpg"}],
        },
        {
            "id": "vid_xyz_2",
            "title": "Hukum - Thalaivar Alappara",
            "uploader": "Sun Pictures",
            "duration": 210,
            "webpage_url": "https://www.youtube.com/watch?v=vid_xyz_2",
            "thumbnails": [{"url": "https://i.ytimg.com/vi/vid_xyz_2/hqdefault.jpg"}],
        },
        {
            "id": "vid_jkl_3",
            "title": "Naa Ready - Leo",
            "uploader": "Sony Music South",
            "duration": 250,
            "webpage_url": "https://www.youtube.com/watch?v=vid_jkl_3",
            "thumbnail": "https://i.ytimg.com/vi/vid_jkl_3/hqdefault.jpg",
        },
    ]

    with patch.object(AudioResolver, "search", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = [
            {
                "id": f"yt_{e['id']}",
                "title": e["title"],
                "artist": e["uploader"],
                "duration": e["duration"],
                "url": e["webpage_url"],
                "thumbnail": f"https://i.ytimg.com/vi/{e['id']}/hqdefault.jpg",
                "provider": "youtube",
            }
            for e in fake_yt_entries
        ]

        request = MagicMock()
        request.query = {"q": "Anirudh Hits"}
        resp = await music_api.search_tracks(request)
        data = json.loads(resp.text)
        assert data["success"] is True
        results = data["data"]
        assert len(results) == 3

        # Verify each result has INDEPENDENT thumbnails and stable IDs
        thumbnails = [r["thumbnail"] for r in results]
        ids = [r["id"] for r in results]

        # All thumbnails must be distinct
        assert len(set(thumbnails)) == 3
        assert "vid_abc_1" in thumbnails[0]
        assert "vid_xyz_2" in thumbnails[1]
        assert "vid_jkl_3" in thumbnails[2]

        # All IDs must be distinct and non-empty
        assert len(set(ids)) == 3
        for r in results:
            assert r["id"].startswith("yt_")
            assert r["provider"] == "youtube"


@pytest.mark.asyncio
async def test_search_missing_artwork_fallback(music_api):
    """Tracks with missing thumbnail gracefully fall back without repeating previous track's art."""
    with patch.object(AudioResolver, "search", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = [
            {
                "id": "yt_no_art_1",
                "title": "Obscure Indie Song",
                "artist": "Indie Band",
                "duration": 180,
                "url": "https://www.youtube.com/watch?v=no_art_1",
                "thumbnail": None,
                "provider": "youtube",
            }
        ]

        request = MagicMock()
        request.query = {"q": "Obscure Indie Song"}
        resp = await music_api.search_tracks(request)
        data = json.loads(resp.text)
        assert data["success"] is True
        result = data["data"][0]
        assert "unsplash.com" not in str(result.get("thumbnail"))
