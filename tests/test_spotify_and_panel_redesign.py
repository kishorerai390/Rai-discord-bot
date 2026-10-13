"""
Unit and Integration Test Suite for:
1. Policy-Compliant Spotify Web API Integration (music_bot/services/spotify_service.py)
2. Clean, Uncluttered Master Control Panel UI Redesign (music_bot/services/player_service.py)
"""

import asyncio
import base64
import json
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import urllib.error

import discord

from music_bot.database.models import QueuedTrack
from music_bot.services.player_service import (
    AudioSettingsSubView,
    AutoDJSubView,
    MusicPlayerService,
    NowPlayingControlView,
    QueueSubView,
    SettingsSubView,
    build_audio_embed,
    build_autodj_embed,
    build_now_playing_embed,
    build_queue_embed,
    build_settings_embed,
)
from music_bot.services.resolver_service import AudioResolver
from music_bot.services.session_service import GuildMusicSession, PlaybackState
from music_bot.services.spotify_service import (
    SpotifyCollection,
    SpotifyItemType,
    SpotifyService,
    SpotifyTrack,
)


class TestSpotifyIntegration(unittest.IsolatedAsyncioTestCase):
    """Test suite for Spotify URL recognition, metadata extraction, rate limits, and compliance."""

    def setUp(self):
        SpotifyService._token_cache = {"access_token": None, "expires_at": 0.0}

    def test_spotify_url_and_uri_recognition(self):
        """1. Verify regex accurately matches track, album, playlist, artist URLs and URIs."""
        # Standard web URLs
        match_track = SpotifyService.match_spotify_link("https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT")
        self.assertIsNotNone(match_track)
        self.assertEqual(match_track[0], SpotifyItemType.TRACK)
        self.assertEqual(match_track[1], "4cOdK2wGLETKBW3PvgPWqT")

        # International localized URLs
        match_intl = SpotifyService.match_spotify_link("https://open.spotify.com/intl-ja/track/4cOdK2wGLETKBW3PvgPWqT?si=abc123")
        self.assertIsNotNone(match_intl)
        self.assertEqual(match_intl[0], SpotifyItemType.TRACK)
        self.assertEqual(match_intl[1], "4cOdK2wGLETKBW3PvgPWqT")

        # Album URLs
        match_album = SpotifyService.match_spotify_link("https://open.spotify.com/album/1DFixLWuPkv3KT3TnV35m3")
        self.assertIsNotNone(match_album)
        self.assertEqual(match_album[0], SpotifyItemType.ALBUM)
        self.assertEqual(match_album[1], "1DFixLWuPkv3KT3TnV35m3")

        # Playlist URLs
        match_playlist = SpotifyService.match_spotify_link("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M")
        self.assertIsNotNone(match_playlist)
        self.assertEqual(match_playlist[0], SpotifyItemType.PLAYLIST)
        self.assertEqual(match_playlist[1], "37i9dQZF1DXcBWIGoYBM5M")

        # Spotify URIs
        match_uri = SpotifyService.match_spotify_link("spotify:track:4cOdK2wGLETKBW3PvgPWqT")
        self.assertIsNotNone(match_uri)
        self.assertEqual(match_uri[0], SpotifyItemType.TRACK)
        self.assertEqual(match_uri[1], "4cOdK2wGLETKBW3PvgPWqT")

        # Non-Spotify URLs
        self.assertIsNone(SpotifyService.match_spotify_link("https://www.youtube.com/watch?v=dQw4w9WgXcQ"))
        self.assertIsNone(SpotifyService.match_spotify_link("https://soundcloud.com/artist/track"))
        self.assertIsNone(SpotifyService.match_spotify_link("lofi hip hop study beats"))

    @patch("music_bot.config.is_spotify_configured", return_value=True)
    @patch("music_bot.config.SPOTIFY_CLIENT_ID", "mock_client_id")
    @patch("music_bot.config.SPOTIFY_CLIENT_SECRET", "mock_client_secret")
    async def test_spotify_token_caching_and_expiration(self, *mocks):
        """2. Verify client credentials flow requests token, caches it, and reuses until near expiration."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__.return_value = mock_response
        mock_response.read.return_value = json.dumps({
            "access_token": "mock_access_token_123",
            "token_type": "Bearer",
            "expires_in": 3600,
        }).encode("utf-8")

        with patch("urllib.request.urlopen", return_value=mock_response) as mock_urlopen:
            token1 = await SpotifyService._get_access_token()
            self.assertEqual(token1, "mock_access_token_123")
            self.assertEqual(mock_urlopen.call_count, 1)

            # Second call should reuse cached token without network request
            token2 = await SpotifyService._get_access_token()
            self.assertEqual(token2, "mock_access_token_123")
            self.assertEqual(mock_urlopen.call_count, 1)

            # Fast-forward time past expiration buffer
            SpotifyService._token_cache["expires_at"] = time.time() + 10  # less than 60s
            token3 = await SpotifyService._get_access_token()
            self.assertEqual(token3, "mock_access_token_123")
            self.assertEqual(mock_urlopen.call_count, 2)

    @patch("music_bot.config.is_spotify_configured", return_value=True)
    async def test_spotify_rate_limit_backoff(self, mock_cfg):
        """3. Verify HTTP 429 rate limit triggers exponential backoff or respects Retry-After."""
        with patch.object(SpotifyService, "_get_access_token", return_value="valid_token"):
            err_429 = urllib.error.HTTPError(
                url="https://api.spotify.com/v1/tracks/123",
                code=429,
                msg="Too Many Requests",
                hdrs={"Retry-After": "1"},
                fp=None,
            )
            success_resp = MagicMock()
            success_resp.status = 200
            success_resp.__enter__.return_value = success_resp
            success_resp.read.return_value = json.dumps({
                "name": "Blinding Lights",
                "artists": [{"name": "The Weeknd"}],
                "duration_ms": 200000,
            }).encode("utf-8")

            # First attempt 429, second attempt succeeds
            with patch("urllib.request.urlopen", side_effect=[err_429, success_resp]):
                data = await SpotifyService._api_get("tracks/123", max_retries=2)
                self.assertIsNotNone(data)
                self.assertEqual(data["name"], "Blinding Lights")

    async def test_spotify_oembed_fallback_when_credentials_missing(self):
        """4. Verify open oEmbed metadata extraction works when developer credentials are not configured."""
        mock_oembed = MagicMock()
        mock_oembed.status = 200
        mock_oembed.__enter__.return_value = mock_oembed
        mock_oembed.read.return_value = json.dumps({
            "title": "Stay With Me",
            "thumbnail_url": "https://i.scdn.co/image/mock_thumb",
        }).encode("utf-8")

        mock_page = MagicMock()
        mock_page.status = 200
        mock_page.__enter__.return_value = mock_page
        mock_page.read.return_value = b"<html><head><title>Stay With Me - song by Miki Matsubara | Spotify</title></head></html>"

        with patch("music_bot.config.is_spotify_configured", return_value=False):
            with patch("urllib.request.urlopen", side_effect=[mock_oembed, mock_page]):
                track = await SpotifyService.resolve_via_oembed("https://open.spotify.com/track/mock123")
                self.assertIsNotNone(track)
                self.assertEqual(track.title, "Stay With Me")
                self.assertEqual(track.artist, "Miki Matsubara")
                self.assertEqual(track.thumbnail_url, "https://i.scdn.co/image/mock_thumb")
                self.assertEqual(track.search_query, "Stay With Me Miki Matsubara")


    def test_spotify_policy_compliant_embeds(self):
        """5. Verify Spotify embeds contain compliance notices and direct Spotify links."""
        track = SpotifyTrack(
            id="test1",
            title="Levitating",
            artist="Dua Lipa",
            album="Future Nostalgia",
            duration_seconds=203,
            url="https://open.spotify.com/track/test1",
            thumbnail_url="https://i.scdn.co/image/test",
        )
        embed = SpotifyService.build_spotify_track_embed(track)
        self.assertEqual(embed.color.value, 0x1DB954)  # Spotify green
        self.assertIn("Levitating", embed.title)
        self.assertIn("Dua Lipa", embed.description)
        self.assertIn("In strict compliance with Spotify Developer Terms", embed.description)
        self.assertIn("https://open.spotify.com/track/test1", embed.description)

        unsupported_embed = SpotifyService.build_spotify_unsupported_embed("https://open.spotify.com/track/unsupported")
        self.assertIn("Spotify Playback Notice", unsupported_embed.title)
        self.assertIn("does not rip, download, or bypass encryption", unsupported_embed.description)
        self.assertIn("https://open.spotify.com/track/unsupported", unsupported_embed.description)


class TestMasterControlPanelRedesign(unittest.IsolatedAsyncioTestCase):
    """Test suite for minimal Master Control Panel and separate feature sub-panels."""

    def setUp(self):
        self.session = GuildMusicSession(guild_id=123456789)
        self.sample_track = QueuedTrack(
            title="Plastic Love",
            artist="Mariya Takeuchi",
            url="https://open.spotify.com/track/sample_spotify_track",
            duration=476,
            requester_id=555666777,
            requester_name="Kishore",
            thumbnail="https://images.unsplash.com/sample_art.jpg",
        )

    def test_minimal_now_playing_embed_structure(self):
        """1. Verify minimal main panel embed displays clean progress, Spotify badge, and voice state."""
        self.session.current_track = self.sample_track
        self.session.state = PlaybackState.PLAYING
        self.session.volume = 75

        embed = build_now_playing_embed(self.session)
        self.assertIn("NOW PLAYING", embed.title)
        self.assertIn("Plastic Love", embed.description)
        self.assertIn("Mariya Takeuchi", embed.description)
        self.assertIn("Spotify Source", embed.description)
        self.assertIn("75%", embed.description)
        self.assertIn("Playing", embed.description)
        self.assertIn("<@555666777>", embed.description)
        self.assertIn("MusicMaid • Lossless Audio", embed.footer.text)

    def test_control_view_12_button_layout_and_rows(self):
        """2. Verify NowPlayingControlView has 12 buttons cleanly organized across rows <= 5."""
        view = NowPlayingControlView(self.session)
        self.assertEqual(len(view.children), 12)

        # Row 0: Playback controls (5 items)
        row_0_ids = [b.custom_id for b in view.children if b.row == 0]
        self.assertEqual(len(row_0_ids), 5)
        self.assertEqual(
            row_0_ids,
            ["music_btn_prev", "music_btn_rewind_10", "music_btn_play_pause", "music_btn_forward_10", "music_btn_skip"],
        )

        # Row 1: Navigation & controls (5 items)
        row_1_ids = [b.custom_id for b in view.children if b.row == 1]
        self.assertEqual(len(row_1_ids), 5)
        self.assertEqual(
            row_1_ids,
            ["music_btn_queue", "music_btn_refresh", "music_btn_nav_audio", "music_btn_nav_autodj", "music_btn_nav_settings"],
        )

        # Row 2: Session controls (2 items)
        row_2_ids = [b.custom_id for b in view.children if b.row == 2]
        self.assertEqual(len(row_2_ids), 2)
        self.assertEqual(row_2_ids, ["music_btn_fav", "music_btn_stop"])

    def test_queue_sub_panel(self):
        """3. Verify QueueSubView and embed provide queue management with Back and Close."""
        self.session.current_track = self.sample_track
        self.session.queue.append(self.sample_track)
        embed = build_queue_embed(self.session)
        self.assertIn("Queue (1 tracks)", embed.title)
        self.assertIn("Plastic Love", embed.description)

        view = QueueSubView(self.session)
        ids = [b.custom_id for b in view.children]
        self.assertIn("sub_queue_shuffle", ids)
        self.assertIn("sub_queue_clear", ids)
        self.assertIn("sub_queue_back", ids)
        self.assertIn("sub_queue_close", ids)

    def test_audio_settings_sub_panel(self):
        """4. Verify AudioSettingsSubView provides volume, DSP EQ presets, Back, and Close."""
        embed = build_audio_embed(self.session)
        self.assertIn("Audio Settings & DSP Filters", embed.title)

        view = AudioSettingsSubView(self.session)
        ids = [b.custom_id for b in view.children]
        # Volume buttons
        self.assertIn("sub_vol_20", ids)
        self.assertIn("sub_vol_50", ids)
        self.assertIn("sub_vol_80", ids)
        self.assertIn("sub_vol_100", ids)
        # EQ presets
        self.assertIn("sub_eq_bass", ids)
        self.assertIn("sub_eq_8d", ids)
        self.assertIn("sub_eq_lofi", ids)
        self.assertIn("sub_eq_vocal", ids)
        self.assertIn("sub_eq_flat", ids)
        # Navigation
        self.assertIn("sub_audio_back", ids)
        self.assertIn("sub_audio_close", ids)

    def test_autodj_sub_panel(self):
        """5. Verify AutoDJSubView provides mode selection, Toggle, Back, and Close."""
        embed = build_autodj_embed(self.session)
        self.assertIn("Auto-DJ Controls", embed.title)
        self.assertIn("Manually queued songs ALWAYS take top priority", embed.description)

        view = AutoDJSubView(self.session)
        ids = [b.custom_id for b in view.children]
        self.assertIn("sub_dj_toggle", ids)
        self.assertIn("sub_dj_energy", ids)
        self.assertIn("sub_dj_chill", ids)
        self.assertIn("sub_dj_discovery", ids)
        self.assertIn("sub_dj_vibe", ids)
        self.assertIn("sub_dj_back", ids)
        self.assertIn("sub_dj_close", ids)

    def test_settings_sub_panel(self):
        """6. Verify SettingsSubView provides 24/7 toggle, Loop, Doctor diagnostics, Back, and Close."""
        embed = build_settings_embed(self.session)
        self.assertIn("Settings & Diagnostics", embed.title)

        view = SettingsSubView(self.session)
        ids = [b.custom_id for b in view.children]
        self.assertIn("sub_set_247", ids)
        self.assertIn("sub_set_loop", ids)
        self.assertIn("sub_set_doc", ids)
        self.assertIn("sub_set_back", ids)
        self.assertIn("sub_set_close", ids)


if __name__ == "__main__":
    unittest.main()
