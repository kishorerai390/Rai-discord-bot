import pytest
from unittest.mock import MagicMock
from web_landing import LANDING_PAGE_HTML
from web_login import LOGIN_PAGE_HTML

def test_landing_page_has_login_button():
    """Verify landing page includes clear login navigation button."""
    assert 'href="/login"' in LANDING_PAGE_HTML
    assert "Sign In" in LANDING_PAGE_HTML
    assert "Login" in LANDING_PAGE_HTML
    assert "syncLiveBotTrack" in LANDING_PAGE_HTML

def test_login_page_structure():
    """Verify login portal renders with Discord auth and passkey options."""
    assert "Sign in to Rem" in LOGIN_PAGE_HTML
    assert "/api/auth/login" in LOGIN_PAGE_HTML
    assert "Continue with Discord" in LOGIN_PAGE_HTML
    assert "rem_avatar_static.png" in LOGIN_PAGE_HTML

@pytest.mark.asyncio
async def test_session_endpoint_active_player_fallback():
    """Verify live bot voice client extraction in session endpoint."""
    from web.music_api import MusicApiRouter
    from aiohttp.test_utils import make_mocked_request

    mock_bot = MagicMock()
    mock_guild = MagicMock()
    mock_guild.id = 999988887777
    mock_guild.name = "Test Discord Guild"
    
    mock_ch = MagicMock()
    mock_ch.name = "anime-lounge"
    mock_ch.id = 98765
    mock_ch.members = []

    # Mock player with real playing track (not MagicMock name)
    class RealVoiceClient:
        def __init__(self):
            self.is_connected = True
            self.is_playing = True
            self.is_paused = False
            self.position = 45000  # 45 seconds
            self.volume = 90
            self.current = None
            self.channel = mock_ch

    class RealTrack:
        def __init__(self):
            self.title = "KALYANI (with Shreya Ghoshal)"
            self.author = "Anirudh Ravichander"
            self.length = 240000  # 240 seconds
            self.thumbnail = "https://example.com/kalyani.jpg"
            self.uri = "https://youtube.com/watch?v=sample"
            self.requester = MagicMock()

    mock_player = RealVoiceClient()
    mock_track = RealTrack()
    mock_player.current = mock_track

    mock_guild.voice_client = mock_player
    mock_bot.get_guild.return_value = mock_guild
    mock_bot.guilds = [mock_guild]

    mock_auth = MagicMock()
    router = MusicApiRouter(mock_auth, bot=mock_bot)
    req = make_mocked_request("GET", "/api/music/session?guild_id=999988887777")

    resp = await router.get_session(req)
    assert resp.status == 200
    import json
    data = json.loads(resp.text)
    assert data["success"] is True
    assert data["data"]["current_track"]["title"] == "KALYANI (with Shreya Ghoshal)"
    assert data["data"]["current_track"]["artist"] == "Anirudh Ravichander"
    assert data["data"]["duration_seconds"] == 240
    assert data["data"]["position_seconds"] == 45
