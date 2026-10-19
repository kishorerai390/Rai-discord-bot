"""
Unit and Integration Test Suite: MusicMaid Branded URL Resolution & OAuth2 Routing.

Validates:
1. PUBLIC_BASE_URL configuration prioritization (custom domain or branded Render hostname).
2. Backward compatibility fallback to MUSICMAID_DEFAULT_URL (rai-discord-bot.onrender.com) when unset.
3. OAuth2 redirect URI dynamic calculation matching /api/auth/callback exactly.
4. Discord OAuth URL generation and code exchange URI consistency.
5. Discord /premium command button link generation with canonical branded URLs.
6. Localhost rejection and input sanitization (rejecting non-public domains).
7. Payment gateway redirect base URL resolution.
"""

from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch
from aiohttp import web

from music_bot.config import (
    get_musicmaid_website_url,
    get_premium_plans_url,
    is_valid_public_https_url,
    MUSICMAID_DEFAULT_URL,
)
from music_bot.commands.music_cog import PremiumLinkView
from web.auth import AuthManager
from web.payment_api import PaymentApiRouter


class TestBrandedUrlAndOAuthRouting(unittest.TestCase):
    """Test suite for configurable PUBLIC_BASE_URL and Discord OAuth2 routing."""

    def test_01_public_base_url_custom_domain(self):
        """1. When PUBLIC_BASE_URL is set to a custom domain, it takes highest precedence."""
        with patch.dict(os.environ, {
            "PUBLIC_BASE_URL": "https://musicmaid.bot",
            "MUSICMAID_WEBSITE_URL": "https://rai-discord-bot.onrender.com",
            "RENDER_EXTERNAL_URL": "https://rai-discord-bot.onrender.com",
        }, clear=False):
            url = get_musicmaid_website_url()
            self.assertEqual(url, "https://musicmaid.bot")

    def test_02_public_base_url_branded_render_subdomain(self):
        """2. When PUBLIC_BASE_URL is set to a renamed Render subdomain, it is respected."""
        with patch.dict(os.environ, {
            "PUBLIC_BASE_URL": "https://musicmaid.onrender.com",
            "MUSICMAID_WEBSITE_URL": "",
        }, clear=False):
            url = get_musicmaid_website_url()
            self.assertEqual(url, "https://musicmaid.onrender.com")

    def test_03_fallback_to_default_production_url(self):
        """3. When no environment variables are set, safely fall back to MUSICMAID_DEFAULT_URL."""
        with patch.dict(os.environ, {
            "PUBLIC_BASE_URL": "",
            "MUSICMAID_WEBSITE_URL": "",
            "RENDER_EXTERNAL_URL": "",
            "PUBLIC_URL": "",
            "WEB_BASE_URL": "",
        }, clear=False):
            url = get_musicmaid_website_url()
            self.assertEqual(url, MUSICMAID_DEFAULT_URL)
            self.assertEqual(url, "https://rai-discord-bot.onrender.com")

    def test_04_reject_invalid_or_localhost_urls(self):
        """4. Reject localhost, raw IP loopbacks, and non-HTTPS/HTTP schemes."""
        self.assertFalse(is_valid_public_https_url("http://localhost:8080"))
        self.assertFalse(is_valid_public_https_url("http://127.0.0.1:3000"))
        self.assertFalse(is_valid_public_https_url("https://192.168.1.100"))
        self.assertFalse(is_valid_public_https_url("ftp://musicmaid.bot"))
        self.assertFalse(is_valid_public_https_url("not_a_valid_url"))
        self.assertTrue(is_valid_public_https_url("https://musicmaid.bot"))
        self.assertTrue(is_valid_public_https_url("https://musicmaid.onrender.com"))

    def test_05_oauth_redirect_uri_with_public_base_url(self):
        """5. OAuth2 redirect URI matches {PUBLIC_BASE_URL}/api/auth/callback exactly."""
        mock_db = MagicMock()
        auth = AuthManager(mock_db)

        with patch.dict(os.environ, {
            "PUBLIC_BASE_URL": "https://musicmaid.bot",
            "DISCORD_REDIRECT_URI": "",
        }, clear=False):
            redirect = auth.get_redirect_uri()
            self.assertEqual(redirect, "https://musicmaid.bot/api/auth/callback")
            canonical = auth.get_canonical_base_url()
            self.assertEqual(canonical, "https://musicmaid.bot")

    def test_06_oauth_redirect_uri_explicit_override(self):
        """6. Explicit DISCORD_REDIRECT_URI is respected when set to a valid public URL."""
        mock_db = MagicMock()
        auth = AuthManager(mock_db)

        with patch.dict(os.environ, {
            "PUBLIC_BASE_URL": "https://musicmaid.bot",
            "DISCORD_REDIRECT_URI": "https://auth.musicmaid.bot/api/auth/callback",
        }, clear=False):
            redirect = auth.get_redirect_uri()
            self.assertEqual(redirect, "https://auth.musicmaid.bot/api/auth/callback")

    def test_07_oauth_redirect_uri_dynamic_request_header(self):
        """7. Incoming request with custom domain via reverse proxy dynamically resolves redirect URI."""
        mock_db = MagicMock()
        auth = AuthManager(mock_db)

        # Create mock request with X-Forwarded headers
        mock_request = MagicMock(spec=web.Request)
        mock_request.scheme = "https"
        mock_request.host = "musicmaid.app"
        mock_request.headers = {
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Host": "musicmaid.app",
        }

        with patch.dict(os.environ, {
            "PUBLIC_BASE_URL": "",
            "MUSICMAID_WEBSITE_URL": "",
            "DISCORD_REDIRECT_URI": "http://localhost:8080/api/auth/callback",
            "RENDER_EXTERNAL_URL": "",
        }, clear=False):
            redirect = auth.get_redirect_uri(mock_request)
            self.assertEqual(redirect, "https://musicmaid.app/api/auth/callback")

    def test_08_premium_command_links_to_branded_url(self):
        """8. Discord /premium command Link button directs to configured branded URL."""
        with patch.dict(os.environ, {
            "PUBLIC_BASE_URL": "https://musicmaid.bot",
        }, clear=False):
            view = PremiumLinkView()
            self.assertGreaterEqual(len(view.children), 1)
            btn = view.children[0]
            self.assertEqual(btn.url, "https://musicmaid.bot")

    def test_09_payment_api_base_url_resolution(self):
        """9. PaymentApiRouter._get_base_url resolves to canonical public URL."""
        mock_bot = MagicMock()
        mock_db = MagicMock()
        mock_auth = MagicMock()
        router = PaymentApiRouter(mock_bot, mock_db, mock_auth)

        mock_request = MagicMock(spec=web.Request)
        mock_request.scheme = "https"
        mock_request.host = "custom.musicmaid.io"
        mock_request.headers = {}

        with patch.dict(os.environ, {
            "PUBLIC_BASE_URL": "https://custom.musicmaid.io",
        }, clear=False):
            base_url = router._get_base_url(mock_request)
            self.assertEqual(base_url, "https://custom.musicmaid.io")


if __name__ == "__main__":
    unittest.main()
