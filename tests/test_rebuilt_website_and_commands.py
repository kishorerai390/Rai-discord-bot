"""
Unit tests verifying the rebuilt website with integrated bot commands and suggestions.
"""

import unittest
import os
from web_landing import LANDING_PAGE_HTML

class TestRebuiltWebsiteAndCommands(unittest.TestCase):

    def test_landing_page_html_integrity(self):
        """Verify landing page HTML is present, non-empty, and valid HTML structure."""
        self.assertIsNotNone(LANDING_PAGE_HTML)
        self.assertTrue(len(LANDING_PAGE_HTML) > 10000)
        self.assertIn("<!DOCTYPE html>", LANDING_PAGE_HTML)
        self.assertIn("<html lang=\"en\"", LANDING_PAGE_HTML)
        self.assertIn("</html>", LANDING_PAGE_HTML)

    def test_bot_commands_directory_integrated(self):
        """Verify the complete bot command suite is integrated into the website."""
        commands_to_check = [
            "/play",
            "/search",
            "/skip",
            "/pause",
            "/resume",
            "/stop",
            "/leave",
            "/speed",
            "/nightcore",
            "/8d",
            "/vaporwave",
            "/karaoke",
            "/cleareffect",
            "/queue",
            "/shuffle",
            "/repeat",
            "/autodj",
            "/247",
            "/debug",
        ]
        for cmd in commands_to_check:
            self.assertIn(cmd, LANDING_PAGE_HTML, f"Expected {cmd} in web_landing.py bot commands directory")

    def test_smart_suggestions_engine(self):
        """Verify the smart suggestions and vibe explorer features are present."""
        vibes_to_check = [
            "Anime Openings",
            "Midnight Lo-Fi Beats",
            "Cyberpunk Drift Phonk",
            "J-Rock & Shonen",
            "Kawaii J-Pop Chill",
            "Retro 80s Synthwave",
        ]
        for vibe in vibes_to_check:
            self.assertIn(vibe, LANDING_PAGE_HTML, f"Expected vibe '{vibe}' in suggestions engine")

    def test_dsp_equalizer_and_karaoke(self):
        """Verify 10-band equalizer presets and karaoke lyrics are embedded."""
        self.assertIn("bassboost", LANDING_PAGE_HTML.lower())
        self.assertIn("nightcore", LANDING_PAGE_HTML.lower())
        self.assertIn("vaporwave", LANDING_PAGE_HTML.lower())
        self.assertIn("31Hz", LANDING_PAGE_HTML)
        self.assertIn("16kHz", LANDING_PAGE_HTML)
        self.assertIn("lyrics-scroll-box", LANDING_PAGE_HTML)
        self.assertIn("queue-list-box", LANDING_PAGE_HTML)

    def test_theme_engine_palettes(self):
        """Verify 4 themes are supported in the rebuilt website."""
        for theme in ["obsidian", "sakura", "cyberpunk", "lofi"]:
            self.assertIn(f'data-theme="{theme}"', LANDING_PAGE_HTML, f"Theme '{theme}' selector missing in landing page CSS")

    def test_dashboard_view_commands_integration(self):
        """Verify DashboardView.tsx contains the command modal and vibe suggestions."""
        view_path = os.path.join(os.path.dirname(__file__), "..", "src", "components", "views", "DashboardView.tsx")
        with open(view_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("isCommandModalOpen", content)
        self.assertIn("Commands (41)", content)
        self.assertIn("vibeChips", content)
        self.assertIn("Vibe Explorer:", content)

    def test_current_logo_updated(self):
        """Verify the current Rem anime avatar is used in web interfaces instead of old badge."""
        from web.ui import UI_HTML
        self.assertIn("/public/rem_avatar_static.png", UI_HTML)
        self.assertNotIn("/public/rem_logo_badge.gif", UI_HTML)
        self.assertIn("/public/rem_avatar_static.png", LANDING_PAGE_HTML)

    def test_tab_2_active_and_clickable(self):
        """Verify Tab 2 in workspace switcher is active, clickable, and not disabled."""
        from web.ui import UI_HTML
        self.assertIn("2. User Dashboard (Turntable & Deck)", UI_HTML)
        self.assertIn('onclick="navigate(\'/dashboard\')"', UI_HTML)
        self.assertIn("ACTIVE", UI_HTML)

    def test_login_loop_prevention_and_guest_controls(self):
        """Verify router navigates to dashboard on auth and guest actions are allowed in music_api."""
        from web.ui import UI_HTML
        from web.music_api import MusicApiRouter
        self.assertIn("window.history.replaceState({}, '', '/dashboard');", UI_HTML)
        self.assertIn("guest_listener_", UI_HTML)
        self.assertTrue(hasattr(MusicApiRouter, "_require_authenticated_user"))

if __name__ == "__main__":
    unittest.main()
